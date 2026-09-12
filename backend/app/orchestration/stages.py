import asyncio
import json
import logging
import time
import uuid
from contextlib import suppress

from app.config import settings
from app.services.stt import transcribe_audio, is_noisy_transcription, is_hallucinated_silence
from app.services.audio_processor import pcm_to_wav, strip_wav_header
from app.services.rag import requires_rag, retrieve_relevant_chunks
from app.services.llm import generate_response_stream
from app.services.sentiment_analyzer import analyze_sentiment, save_sentiment
from app.services.sentences import take_complete_sentences
from app.services.tts import synthesize_speech_stream, strip_markdown
from app.services.session import save_turn
from app.websocket.manager import manager
from app.orchestration.pipeline import (
    SessionPipelineState,
    TextInMessage,
    SentenceMessage,
    TurnComplete,
    safe_put_nowait,
    make_event,
)

logger = logging.getLogger(__name__)

# Spoken while the model is still thinking. Static on purpose: generating these
# with an LLM would add exactly the latency they exist to mask.
FILLER_PHRASES = {
    "thinking": "Let me check that for you.",
    "searching": "Searching our records now.",
}


def _spawn(state: SessionPipelineState, coro) -> asyncio.Task:
    """Run work off the critical path, keeping a strong reference to it."""
    task = asyncio.create_task(coro)
    state.background_tasks.add(task)
    task.add_done_callback(state.background_tasks.discard)
    return task


async def _guarded(state: SessionPipelineState, name: str, body) -> None:
    """Run a stage loop body, surviving anything except cancellation.

    Previously a single exception killed the stage task outright: the session
    went permanently deaf or mute with nothing reported to the client.
    """
    try:
        await body()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("STAGE_ERROR stage=%s session=%s error=%s", name, state.session_id, exc)
        safe_put_nowait(
            state.ws_event_queue,
            make_event(state, "error", message=f"stage_error:{name}:{type(exc).__name__}"),
        )


# --- ws in -------------------------------------------------------------------


async def ws_in_task(state: SessionPipelineState) -> None:
    while True:
        msg = await state.websocket.receive()
        if msg["type"] == "websocket.disconnect":
            safe_put_nowait(state.control_queue, {"type": "disconnect"})
            break
        if "bytes" in msg:
            safe_put_nowait(state.audio_in_queue, msg["bytes"])
            logger.debug("AUDIO_CHUNK_RECEIVED session=%s bytes=%s", state.session_id, len(msg["bytes"]))
            continue
        if "text" not in msg:
            continue

        try:
            data = json.loads(msg["text"])
        except (json.JSONDecodeError, TypeError):
            logger.warning("WS_BAD_JSON session=%s", state.session_id)
            continue
        if not isinstance(data, dict):
            continue

        msg_type = data.get("type")
        if msg_type == "ping":
            with suppress(Exception):
                await state.websocket.send_text(json.dumps({"type": "pong"}))
        elif msg_type == "stop_call":
            safe_put_nowait(state.control_queue, {"type": "stop_call"})
            break
        elif msg_type == "start_call":
            state.call_started = True
            logger.info("START_CALL_RECEIVED session=%s", state.session_id)
            safe_put_nowait(state.control_queue, {"type": "start_call"})
        elif msg_type == "stop_playback":
            safe_put_nowait(state.control_queue, {"type": "cancel_turn"})
        elif msg_type == "stop_listening":
            safe_put_nowait(state.control_queue, {"type": "force_stt", "data": data})
        elif msg_type in ("transcript", "external_transcript"):
            safe_put_nowait(state.control_queue, {"type": "external_transcript", "data": data})
        elif msg_type == "voice_select":
            safe_put_nowait(state.control_queue, {"type": "voice_select", "data": data})
        elif msg_type == "playback_state":
            # The browser is the only thing that knows when its speakers go
            # quiet; the server finishes sending long before playback ends.
            safe_put_nowait(state.control_queue, {"type": "playback_state", "data": data})


# --- vad + stt ---------------------------------------------------------------


async def vad_stt_task(state: SessionPipelineState, audio_executor) -> None:
    logger.info("VAD_STT_TASK_STARTED session=%s", state.session_id)
    # WebRTC VAD accepts only 10, 20 or 30 ms PCM frames.
    frame_size = int(settings.audio_sample_rate * 2 * (30 / 1000))
    loop = asyncio.get_running_loop()

    while True:
        chunk = await state.audio_in_queue.get()
        try:
            if chunk is None:
                break
            if not state.call_started:
                continue

            state.user_pcm_buffer.extend(chunk)

            frame_audio, speech_ended, speech_onset, speech_end = await loop.run_in_executor(
                audio_executor, state.vad.process_bytes, chunk, frame_size
            )

            # Barge-in fires the instant the user starts talking, not after
            # they finish and a further silence_threshold_ms has elapsed.
            if state.vad.onset_pending:
                state.vad.onset_pending = False
                state.speech_started.set()

            if not (speech_ended and frame_audio):
                continue

            logger.info("SPEECH_ENDED session=%s frame_bytes=%s", state.session_id, len(frame_audio))
            state.speech_detected.set()

            recording_start_ms = (
                int((speech_onset - state.call_start_time) * 1000)
                if speech_onset is not None and state.call_start_time is not None
                else None
            )
            recording_end_ms = (
                int((speech_end - state.call_start_time) * 1000)
                if speech_end is not None and state.call_start_time is not None
                else None
            )

            # Dispatch STT without blocking: while it is in flight the VAD loop
            # keeps running, so barge-in and the next utterance still register.
            stt_task = asyncio.create_task(_transcribe(frame_audio, audio_executor))
            safe_put_nowait(
                state.stt_pending_queue,
                (stt_task, recording_start_ms, recording_end_ms, state.vad.last_voiced_ms),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("VAD_STT_TASK_ERROR session=%s error=%s", state.session_id, exc)
            safe_put_nowait(
                state.ws_event_queue,
                make_event(state, "error", message=f"vad_error:{type(exc).__name__}"),
            )
        finally:
            state.audio_in_queue.task_done()


async def _transcribe(frame_audio: bytes, audio_executor) -> tuple[str, int]:
    loop = asyncio.get_running_loop()
    wav_audio = await loop.run_in_executor(
        audio_executor, pcm_to_wav, frame_audio, settings.audio_sample_rate
    )
    start = time.perf_counter()
    text = await asyncio.wait_for(transcribe_audio(wav_audio), timeout=15)
    return text, int((time.perf_counter() - start) * 1000)


async def stt_collect_task(state: SessionPipelineState) -> None:
    """Consume STT results in FIFO order so utterances cannot overtake."""
    while True:
        item = await state.stt_pending_queue.get()
        if item is None:
            break
        stt_task, recording_start_ms, recording_end_ms, voiced_ms = item
        try:
            user_text, stt_latency_ms = await stt_task
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            safe_put_nowait(state.ws_event_queue, make_event(state, "error", message="stt_timeout"))
            continue
        except Exception as exc:
            logger.exception("STT_FAILED session=%s error=%s", state.session_id, exc)
            safe_put_nowait(
                state.ws_event_queue,
                make_event(state, "error", message=f"stt_failed:{type(exc).__name__}"),
            )
            continue

        logger.info("STT_RESULT session=%s text=%r latency_ms=%s", state.session_id, user_text, stt_latency_ms)

        if (
            not user_text
            or is_noisy_transcription(user_text)
            or is_hallucinated_silence(user_text, voiced_ms)
        ):
            logger.info(
                "STT_DISCARDED session=%s text=%r voiced_ms=%s",
                state.session_id, user_text, voiced_ms,
            )
            safe_put_nowait(
                state.ws_event_queue,
                make_event(state, "error", message="empty_transcript", stt_latency_ms=stt_latency_ms),
            )
            continue

        safe_put_nowait(
            state.ws_event_queue,
            make_event(state, "transcript_final", role="user", text=user_text, stt_latency_ms=stt_latency_ms),
        )
        safe_put_nowait(
            state.text_in_queue,
            TextInMessage(
                session_id=state.session_id,
                text=user_text,
                stt_latency_ms=stt_latency_ms,
                recording_start_ms=recording_start_ms,
                recording_end_ms=recording_end_ms,
            ),
        )


# --- rag + llm ---------------------------------------------------------------


async def rag_llm_task(state: SessionPipelineState, embedding_executor) -> None:
    while True:
        msg = await state.text_in_queue.get()
        try:
            if msg is None:
                break

            # A turn is only finished when its audio has been sent, not when
            # the LLM stops streaming. Starting the next turn at LLM
            # completion left the previous turn's audio still draining to the
            # browser, so the caller heard two replies talking over each other.
            await _await_playback_finished(state)

            turn_id = str(uuid.uuid4())
            state.current_turn_id = turn_id

            async def _body():
                subtask = asyncio.create_task(_run_llm_turn(state, msg, turn_id, embedding_executor))
                state.active_llm_subtask = subtask
                try:
                    with suppress(asyncio.CancelledError):
                        await subtask
                finally:
                    state.active_llm_subtask = None

            await _guarded(state, "rag_llm", _body)
        finally:
            state.text_in_queue.task_done()


async def _await_speakers_quiet(state: SessionPipelineState, turn_id: str) -> None:
    """Block until the caller's speakers have actually gone quiet.

    Prefers the browser's own report; falls back to the projected end of the
    audio already sent, so a lost or missing message cannot hang the turn.
    """
    hard_stop = time.perf_counter() + 120
    while True:
        if state.current_turn_id != turn_id:
            return                      # barge-in or a newer turn took over
        if state.playback_finished.is_set():
            return                      # browser says it has finished
        now = time.perf_counter()
        if now >= hard_stop:
            logger.warning("PLAYBACK_HARD_STOP session=%s", state.session_id)
            return
        remaining = state.audio_playback_deadline - now
        if remaining <= 0 and state.audio_out_queue.empty():
            return                      # everything sent has had time to play
        await asyncio.sleep(min(0.05, max(0.01, remaining)) if remaining > 0 else 0.02)


async def _await_playback_finished(state: SessionPipelineState, timeout: float = 60.0) -> None:
    """Block until the agent has finished speaking the previous turn."""
    deadline = time.perf_counter() + timeout
    while state.is_speaking and time.perf_counter() < deadline:
        await asyncio.sleep(0.02)
    if state.is_speaking:
        logger.warning("PLAYBACK_WAIT_EXPIRED session=%s", state.session_id)


async def _persist_user_turn(state: SessionPipelineState, msg: TextInMessage) -> str | None:
    """Write the user turn. Deliberately off the critical path."""
    try:
        seq = state.next_sequence_number
        state.next_sequence_number += 1
        return await save_turn(
            state.db_session_id,
            "user",
            msg.text,
            # None, not 0: a user turn has no response latency, and a stored 0
            # was being averaged in as if it were a real measurement.
            latency_ms=None,
            stt_latency_ms=msg.stt_latency_ms,
            recording_start_ms=msg.recording_start_ms,
            recording_end_ms=msg.recording_end_ms,
            sequence_number=seq,
        )
    except Exception:
        logger.exception("SAVE_USER_TURN_FAILED session=%s", state.session_id)
        return None


async def _analyse_sentiment(state: SessionPipelineState, text: str, user_turn: asyncio.Task) -> None:
    """Sentiment is analytics, not part of the response. Never block on it."""
    try:
        sentiment = await analyze_sentiment(text)
        safe_put_nowait(state.ws_event_queue, make_event(state, "sentiment", label=sentiment))
        user_message_id = await user_turn
        if user_message_id:
            await save_sentiment(state.db_session_id, user_message_id, sentiment)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("SENTIMENT_FAILED session=%s", state.session_id)


async def _run_llm_turn(
    state: SessionPipelineState,
    msg: TextInMessage,
    turn_id: str,
    embedding_executor,
) -> None:
    state.conversation_mgr.append_user(msg.text)

    safe_put_nowait(state.ws_event_queue, make_event(state, "turn_started", turn_id=turn_id))
    logger.info("TURN_STARTED session=%s turn_id=%s", state.session_id, turn_id)
    state.turn_started_at = time.perf_counter()
    state.is_speaking = True
    state.playback_finished.clear()
    state.audio_playback_deadline = 0.0
    # Stop the VAD building an utterance out of the agent's own audio coming
    # back through the caller's microphone. The client still detects genuine
    # barge-in by energy and sends stop_playback, which unmutes below.
    if state.vad is not None:
        state.vad.muted = True
    safe_put_nowait(state.ws_event_queue, make_event(state, "status", message="thinking"))

    # Persistence and sentiment run alongside the LLM, not before it.
    user_turn = _spawn(state, _persist_user_turn(state, msg))
    _spawn(state, _analyse_sentiment(state, msg.text, user_turn))

    context = []
    if requires_rag(msg.text):
        safe_put_nowait(state.ws_event_queue, make_event(state, "status", message="retrieving_context"))
        try:
            context = await retrieve_relevant_chunks(
                msg.text,
                persona_id=state.persona_id,
                preferred_document_ids=state.active_document_ids,
            )
        except Exception:
            logger.exception("RAG_FAILED session=%s", state.session_id)

    full_response = ""
    buffer = ""
    sentence_idx = 0
    first_audio_sent = False
    llm_start = time.perf_counter()

    async def _filler_monitor():
        await asyncio.sleep(settings.filler_threshold_ms / 1000)
        if state.current_turn_id == turn_id:
            kind = "searching" if context else "thinking"
            safe_put_nowait(
                state.ws_event_queue,
                make_event(state, "filler", text=FILLER_PHRASES[kind]),
            )

    filler = asyncio.create_task(_filler_monitor())

    try:
        async for chunk in generate_response_stream(
            state.conversation_mgr.get_history(),
            state.system_prompt,
            context=context if context else None,
        ):
            if state.current_turn_id != turn_id:
                break
            full_response += chunk
            buffer += chunk
            # Pure CPU. This used to be an LLM round-trip per stream chunk.
            sentences, buffer = take_complete_sentences(buffer)
            for sentence in sentences:
                if not first_audio_sent:
                    first_audio_sent = True
                    safe_put_nowait(state.ws_event_queue, make_event(state, "status", message="speaking"))
                safe_put_nowait(
                    state.sentence_queue,
                    SentenceMessage(
                        text=sentence,
                        turn_id=turn_id,
                        index=sentence_idx,
                        first_sentence=(sentence_idx == 0),
                    ),
                )
                sentence_idx += 1
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("LLM_FAILED session=%s turn_id=%s", state.session_id, turn_id)
        state.is_speaking = False
        if state.vad is not None:
            state.vad.muted = False
        safe_put_nowait(
            state.ws_event_queue,
            make_event(state, "error", message=f"llm_failed:{type(exc).__name__}"),
        )
        safe_put_nowait(state.ws_event_queue, make_event(state, "status", message="idle"))
        return
    finally:
        filler.cancel()
        with suppress(asyncio.CancelledError):
            await filler

    if buffer.strip() and state.current_turn_id == turn_id:
        safe_put_nowait(
            state.sentence_queue,
            SentenceMessage(
                text=buffer.strip(),
                turn_id=turn_id,
                index=sentence_idx,
                first_sentence=(sentence_idx == 0),
            ),
        )
        sentence_idx += 1

    llm_latency_ms = int((time.perf_counter() - llm_start) * 1000)
    total_turn_latency_ms = (
        int((time.perf_counter() - state.turn_started_at) * 1000) if state.turn_started_at else 0
    )
    ai_recording_start_ms = (
        int((state.turn_started_at - state.call_start_time) * 1000)
        if state.turn_started_at is not None and state.call_start_time is not None
        else None
    )

    safe_put_nowait(
        state.sentence_queue,
        TurnComplete(
            turn_id=turn_id,
            llm_latency_ms=llm_latency_ms,
            full_response=full_response,
            total_turn_latency_ms=total_turn_latency_ms,
            stt_latency_ms=msg.stt_latency_ms,
            ai_recording_start_ms=ai_recording_start_ms,
            db_session_id=state.db_session_id,
        ),
    )

    state.conversation_mgr.append_assistant(full_response)
    safe_put_nowait(
        state.ws_event_queue,
        # The UI renders this as plain text, so send what was actually spoken
        # rather than the raw model output with its markdown still in it.
        make_event(state, "transcript_final", role="assistant", text=strip_markdown(full_response)),
    )


# --- tts ---------------------------------------------------------------------


async def tts_task(state: SessionPipelineState, audio_executor) -> None:
    while True:
        msg = await state.sentence_queue.get()
        try:
            if msg is None:
                break
            if isinstance(msg, TurnComplete):
                await _guarded(state, "turn_complete", lambda: _finish_turn(state, msg))
                continue
            if msg.turn_id != state.current_turn_id:
                continue

            async def _body():
                subtask = asyncio.create_task(_synthesize_sentence(state, msg, audio_executor))
                state.active_tts_subtask = subtask
                try:
                    with suppress(asyncio.CancelledError):
                        await subtask
                finally:
                    state.active_tts_subtask = None

            await _guarded(state, "tts", _body)
        finally:
            state.sentence_queue.task_done()


async def _finish_turn(state: SessionPipelineState, msg: TurnComplete) -> None:
    # is_speaking stays true until the queued audio has actually been handed to
    # the socket. Clearing it here made the supervisor ignore barge-in for the
    # whole tail of the reply, so the user could not interrupt the last
    # sentences the agent was still speaking.
    await _await_speakers_quiet(state, msg.turn_id)
    state.is_speaking = False
    if state.vad is not None:
        state.vad.muted = False
    ai_recording_end_ms = (
        int((time.perf_counter() - state.call_start_time) * 1000)
        if state.call_start_time is not None
        else None
    )

    seq = state.next_sequence_number
    state.next_sequence_number += 1
    _spawn(state, _save_assistant_turn(state, msg, ai_recording_end_ms, seq))

    if state.call_start_time is not None:
        manager.finish_ai_segment(
            state.session_id, int((time.perf_counter() - state.call_start_time) * 1000)
        )

    safe_put_nowait(
        state.ws_event_queue,
        make_event(state, "turn_ended", turn_id=msg.turn_id, llm_latency_ms=msg.llm_latency_ms),
    )
    logger.info("TURN_ENDED session=%s turn_id=%s llm_latency_ms=%s", state.session_id, msg.turn_id, msg.llm_latency_ms)
    safe_put_nowait(
        state.ws_event_queue,
        make_event(
            state,
            "latencies",
            stt=msg.stt_latency_ms,
            llm=msg.llm_latency_ms,
            # Measured on the first sentence of this turn, not hardcoded None.
            ttsFirstAudio=state.last_tts_first_audio_ms,
            total=msg.total_turn_latency_ms,
        ),
    )


async def _save_assistant_turn(state, msg: TurnComplete, end_ms: int | None, seq: int) -> None:
    try:
        await save_turn(
            state.db_session_id,
            "assistant",
            msg.full_response,
            latency_ms=msg.total_turn_latency_ms,
            interrupted=False,
            stt_latency_ms=msg.stt_latency_ms,
            llm_latency_ms=msg.llm_latency_ms,
            tts_first_audio_latency_ms=state.last_tts_first_audio_ms,
            recording_start_ms=msg.ai_recording_start_ms,
            recording_end_ms=end_ms,
            sequence_number=seq,
        )
    except Exception:
        logger.exception("SAVE_ASSISTANT_TURN_FAILED session=%s", state.session_id)


async def _synthesize_sentence(
    state: SessionPipelineState,
    msg: SentenceMessage,
    audio_executor,
) -> None:
    sentence_start_time = time.perf_counter()
    first_chunk = True
    try:
        spoken = strip_markdown(msg.text)
        if not spoken:
            return
        async for chunk in synthesize_speech_stream(spoken, state.voice_id):
            if msg.turn_id != state.current_turn_id:
                break
            if first_chunk:
                first_chunk = False
                latency_ms = int((time.perf_counter() - sentence_start_time) * 1000)
                if msg.first_sentence:
                    state.last_tts_first_audio_ms = latency_ms
                safe_put_nowait(
                    state.ws_event_queue,
                    make_event(state, "response_audio", turn_id=msg.turn_id, latency_ms=latency_ms),
                )
                logger.info(
                    "RESPONSE_AUDIO_FIRST session=%s turn_id=%s latency_ms=%s",
                    state.session_id, msg.turn_id, latency_ms,
                )
                if msg.first_sentence and state.call_start_time is not None:
                    manager.start_ai_segment(
                        state.session_id,
                        int((time.perf_counter() - state.call_start_time) * 1000),
                    )
            pcm = strip_wav_header(bytes(chunk))
            manager.append_ai_audio(state.session_id, pcm)
            # Extend the projected end of playback by this chunk's duration.
            duration = len(pcm) / (settings.audio_sample_rate * 2)
            state.audio_playback_deadline = (
                max(time.perf_counter(), state.audio_playback_deadline) + duration
            )
            safe_put_nowait(state.audio_out_queue, bytes(chunk))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("TTS_FAILED session=%s", state.session_id)
        safe_put_nowait(
            state.ws_event_queue,
            make_event(state, "error", message=f"tts_failed:{type(exc).__name__}"),
        )


# --- ws out ------------------------------------------------------------------


async def ws_out_task(state: SessionPipelineState) -> None:
    while True:
        # Events take priority over audio, but never starve it: at most one
        # batch of events is drained before audio gets a turn.
        drained = 0
        while drained < 16:
            try:
                event = state.ws_event_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            try:
                await state.websocket.send_json(event)
            except Exception:
                return
            drained += 1

        try:
            audio_chunk = state.audio_out_queue.get_nowait()
        except asyncio.QueueEmpty:
            if drained:
                continue
            try:
                audio_chunk = await asyncio.wait_for(state.audio_out_queue.get(), timeout=0.02)
            except asyncio.TimeoutError:
                continue
        if audio_chunk is None:
            break
        try:
            await state.websocket.send_bytes(audio_chunk)
        except Exception:
            safe_put_nowait(state.control_queue, {"type": "disconnect"})
            break


# --- supervisor --------------------------------------------------------------


async def supervisor_task(state: SessionPipelineState) -> None:
    """Interrupt the agent the moment the user starts speaking."""
    while True:
        await state.speech_started.wait()
        state.speech_started.clear()
        if not state.is_speaking:
            continue
        await _guarded(state, "barge_in", lambda: _cancel_current_turn(state))


async def _cancel_current_turn(state: SessionPipelineState) -> None:
    state.current_turn_id = None
    for attr in ("active_llm_subtask", "active_tts_subtask"):
        subtask = getattr(state, attr)
        if subtask is not None and not subtask.done():
            subtask.cancel()
            with suppress(asyncio.CancelledError):
                await subtask

    for queue in (state.sentence_queue, state.audio_out_queue):
        while not queue.empty():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    # Close the segment so the interrupted reply still appears in the saved
    # call recording instead of being discarded with the buffer.
    if state.call_start_time is not None:
        manager.finish_ai_segment(
            state.session_id, int((time.perf_counter() - state.call_start_time) * 1000)
        )

    state.is_speaking = False
    if state.vad is not None:
        state.vad.muted = False
    safe_put_nowait(state.ws_event_queue, make_event(state, "turn_ended", reason="interrupted"))
    safe_put_nowait(state.ws_event_queue, make_event(state, "status", message="interrupted"))
    logger.info("BARGE_IN session=%s", state.session_id)
