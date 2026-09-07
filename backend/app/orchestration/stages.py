import asyncio
import json
import logging
import time
import uuid
from contextlib import suppress
from datetime import datetime, timezone

from app.config import settings
from app.services.stt import transcribe_audio, is_noisy_transcription
from app.services.audio_processor import decode_to_pcm, pcm_to_wav, compose_call_recording
from app.services.rag import requires_rag, retrieve_relevant_chunks
from app.services.llm import generate_response_stream, get_persona_system_prompt
from app.services.sentiment_analyzer import analyze_sentiment
from app.services.sentences import split_sentences
from app.services.tts import synthesize_speech_stream, strip_markdown
from app.services.session import save_turn
from app.websocket.manager import manager, _append_log
from app.orchestration.pipeline import (
    SessionPipelineState,
    TextInMessage,
    SentenceMessage,
    TurnComplete,
    safe_put_nowait,
    make_event,
)

logger = logging.getLogger(__name__)


async def ws_in_task(state: SessionPipelineState) -> None:
    while True:
        msg = await state.websocket.receive()
        if msg["type"] == "websocket.disconnect":
            safe_put_nowait(state.control_queue, {"type": "disconnect"})
            break
        if "bytes" in msg:
            safe_put_nowait(state.audio_in_queue, msg["bytes"])
        elif "text" in msg:
            data = json.loads(msg["text"])
            if data.get("type") == "ping":
                await state.websocket.send_text(json.dumps({"type": "pong"}))
                continue
            if data.get("type") == "stop_call":
                safe_put_nowait(state.control_queue, {"type": "stop_call"})
                break
            if data.get("type") == "start_call":
                state.call_started = True
                safe_put_nowait(state.control_queue, {"type": "start_call"})
                continue
            if data.get("type") == "stop_playback":
                safe_put_nowait(state.control_queue, {"type": "cancel_turn"})
            elif data.get("type") == "stop_listening":
                safe_put_nowait(state.control_queue, {"type": "force_stt", "data": data})
            elif data.get("type") == "transcript":
                safe_put_nowait(state.control_queue, {"type": "external_transcript", "data": data})
            elif data.get("type") == "voice_select":
                safe_put_nowait(state.control_queue, {"type": "voice_select", "data": data})


async def vad_stt_task(state: SessionPipelineState, audio_executor) -> None:
    while True:
        chunk = await state.audio_in_queue.get()
        if chunk is None:
            state.audio_in_queue.task_done()
            break
        if not state.call_started:
            state.audio_in_queue.task_done()
            continue
        try:
            pcm = await asyncio.get_running_loop().run_in_executor(
                audio_executor, decode_to_pcm, chunk, settings.audio_sample_rate
            )
        except Exception:
            state.audio_in_queue.task_done()
            continue

        state.user_pcm_buffer.extend(pcm)

        vad_frame_ms = 32
        frame_size = int(settings.audio_sample_rate * 2 * (vad_frame_ms / 1000))
        frame_audio, speech_ended, speech_onset, speech_end = await asyncio.get_running_loop().run_in_executor(
            audio_executor, state.vad.process_bytes, pcm, frame_size
        )

        if speech_ended and frame_audio:
            state.speech_detected.set()

        if not speech_ended:
            state.audio_in_queue.task_done()
            continue

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

        wav_audio = await asyncio.get_running_loop().run_in_executor(
            audio_executor, pcm_to_wav, frame_audio, settings.audio_sample_rate
        )

        stt_start = time.perf_counter()
        try:
            user_text = await asyncio.wait_for(transcribe_audio(wav_audio), timeout=15)
        except asyncio.TimeoutError:
            state.audio_in_queue.task_done()
            safe_put_nowait(state.ws_event_queue, make_event(state, "error", message="stt_timeout"))
            continue

        stt_latency_ms = int((time.perf_counter() - stt_start) * 1000)

        if not user_text or is_noisy_transcription(user_text):
            state.audio_in_queue.task_done()
            safe_put_nowait(
                state.ws_event_queue,
                make_event(state, "status", message="empty_transcript", stt_latency_ms=stt_latency_ms),
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
        state.audio_in_queue.task_done()


async def rag_llm_task(state: SessionPipelineState, embedding_executor) -> None:
    while True:
        msg = await state.text_in_queue.get()
        if msg is None:
            state.text_in_queue.task_done()
            break

        turn_id = str(uuid.uuid4())
        state.current_turn_id = turn_id

        try:
            user_message_id = await save_turn(
                state.db_session_id,
                "user",
                msg.text,
                latency_ms=0,
                stt_latency_ms=msg.stt_latency_ms,
                recording_start_ms=msg.recording_start_ms,
                recording_end_ms=msg.recording_end_ms,
            )
        except Exception:
            user_message_id = None

        subtask = asyncio.create_task(
            _run_llm_turn(state, msg, turn_id, embedding_executor, user_message_id)
        )
        state.active_llm_subtask = subtask
        with suppress(asyncio.CancelledError):
            await subtask
        state.active_llm_subtask = None
        state.text_in_queue.task_done()


async def _run_llm_turn(
    state: SessionPipelineState,
    msg: TextInMessage,
    turn_id: str,
    embedding_executor,
    user_message_id: str | None,
) -> None:
    state.conversation_mgr.append_user(msg.text)

    safe_put_nowait(state.ws_event_queue, make_event(state, "turn_started", turn_id=turn_id))
    state.turn_started_at = time.perf_counter()

    try:
        sentiment = await analyze_sentiment(msg.text)
        safe_put_nowait(state.ws_event_queue, make_event(state, "sentiment", label=sentiment))
    except Exception:
        sentiment = "neutral"

    context = []
    if requires_rag(msg.text):
        try:
            context = await retrieve_relevant_chunks(msg.text, session_id=state.db_session_id)
        except Exception:
            pass

    system_instruction = await get_persona_system_prompt(state.persona_id)

    state.is_speaking = True
    safe_put_nowait(state.ws_event_queue, make_event(state, "status", message="thinking"))
    full_response = ""
    buffer = ""
    sentence_idx = 0
    first_audio_sent = False
    llm_start = time.perf_counter()

    async def _filler_monitor():
        await asyncio.sleep(settings.filler_threshold_ms / 1000)
        if state.current_turn_id == turn_id:
            safe_put_nowait(state.ws_event_queue, make_event(state, "filler"))

    filler = asyncio.create_task(_filler_monitor())

    try:
        async for chunk in generate_response_stream(
            state.conversation_mgr.get_history(),
            system_instruction,
            context=context if context else None,
        ):
            if state.current_turn_id != turn_id:
                break
            full_response += chunk
            buffer += chunk
            sentences = await split_sentences(buffer)
            while len(sentences) > 1:
                sentence = sentences.pop(0)
                buffer = buffer[len(sentence):].lstrip()
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
                safe_put_nowait(
                    state.ws_event_queue,
                    make_event(state, "response_text", turn_id=turn_id, text=sentence, index=sentence_idx),
                )
                sentence_idx += 1
                await asyncio.sleep(0)
    except asyncio.CancelledError:
        raise
    finally:
        filler.cancel()
        with suppress(asyncio.CancelledError):
            await filler

    if buffer.strip() and state.current_turn_id == turn_id:
        safe_put_nowait(
            state.sentence_queue,
            SentenceMessage(text=buffer.strip(), turn_id=turn_id, index=sentence_idx),
        )
        safe_put_nowait(
            state.ws_event_queue,
            make_event(state, "response_text", turn_id=turn_id, text=buffer.strip(), index=sentence_idx),
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
        make_event(state, "transcript_final", role="assistant", text=full_response),
    )


async def tts_task(state: SessionPipelineState, audio_executor) -> None:
    while True:
        msg = await state.sentence_queue.get()
        if isinstance(msg, TurnComplete):
            state.is_speaking = False
            ai_recording_end_ms = (
                int((time.perf_counter() - state.call_start_time) * 1000)
                if state.call_start_time is not None
                else None
            )
            try:
                await save_turn(
                    state.db_session_id,
                    "assistant",
                    msg.full_response,
                    latency_ms=msg.total_turn_latency_ms,
                    interrupted=False,
                    stt_latency_ms=msg.stt_latency_ms,
                    llm_latency_ms=msg.llm_latency_ms,
                    recording_start_ms=msg.ai_recording_start_ms,
                    recording_end_ms=ai_recording_end_ms,
                )
            except Exception:
                pass
            if state.call_start_time is not None:
                manager.finish_ai_segment(
                    state.session_id,
                    int((time.perf_counter() - state.call_start_time) * 1000),
                )
            safe_put_nowait(
                state.ws_event_queue,
                make_event(state, "turn_complete", turn_id=msg.turn_id, llm_latency_ms=msg.llm_latency_ms),
            )
            state.sentence_queue.task_done()
            continue
        if msg.turn_id != state.current_turn_id:
            state.sentence_queue.task_done()
            continue

        subtask = asyncio.create_task(_synthesize_sentence(state, msg, audio_executor))
        state.active_tts_subtask = subtask
        with suppress(asyncio.CancelledError):
            await subtask
        state.active_tts_subtask = None
        state.sentence_queue.task_done()


async def _synthesize_sentence(
    state: SessionPipelineState,
    msg: SentenceMessage,
    audio_executor,
) -> None:
    sentence_start_time = time.perf_counter()
    first_chunk = True
    try:
        spoken = await asyncio.get_running_loop().run_in_executor(
            audio_executor, strip_markdown, msg.text
        )
        async for chunk in synthesize_speech_stream(spoken, state.voice_id):
            if msg.turn_id != state.current_turn_id:
                break
            if first_chunk:
                first_chunk = False
                safe_put_nowait(
                    state.ws_event_queue,
                    make_event(
                        state,
                        "response_audio",
                        turn_id=msg.turn_id,
                        latency_ms=int((time.perf_counter() - sentence_start_time) * 1000),
                    ),
                )
                if msg.first_sentence and state.call_start_time is not None:
                    manager.start_ai_segment(
                        state.session_id,
                        int((time.perf_counter() - state.call_start_time) * 1000),
                    )
            manager.append_ai_audio(state.session_id, bytes(chunk))
            safe_put_nowait(state.audio_out_queue, bytes(chunk))
            await asyncio.sleep(0)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        safe_put_nowait(state.ws_event_queue, make_event(state, "error", message=f"tts_failed:{exc}"))


async def ws_out_task(state: SessionPipelineState) -> None:
    while True:
        event = None
        try:
            event = state.ws_event_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass

        if event is None:
            try:
                audio_chunk = await asyncio.wait_for(
                    state.audio_out_queue.get(), timeout=0.05
                )
            except asyncio.TimeoutError:
                continue
            if audio_chunk is None:
                break
            try:
                await state.websocket.send_bytes(audio_chunk)
            except Exception:
                safe_put_nowait(state.control_queue, {"type": "disconnect"})
                break
            continue

        if event.get("type") == "disconnect":
            break
        if event.get("type") == "stop_call":
            try:
                await state.websocket.close()
            except Exception:
                pass
            break

        try:
            await state.websocket.send_json(event)
        except Exception:
            break


async def supervisor_task(state: SessionPipelineState) -> None:
    while True:
        await state.speech_detected.wait()
        state.speech_detected.clear()

        if state.is_speaking:
            state.current_turn_id = None

            for subtask_attr in ("active_llm_subtask", "active_tts_subtask"):
                subtask = getattr(state, subtask_attr)
                if subtask is not None and not subtask.done():
                    subtask.cancel()
                    with suppress(asyncio.CancelledError):
                        await subtask

            while not state.sentence_queue.empty():
                try:
                    state.sentence_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            while not state.audio_out_queue.empty():
                try:
                    state.audio_out_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

            state.is_speaking = False
            safe_put_nowait(state.ws_event_queue, make_event(state, "turn_ended", reason="interrupted"))
            safe_put_nowait(state.ws_event_queue, make_event(state, "status", message="idle"))
