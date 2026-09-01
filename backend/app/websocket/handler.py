import json
import logging
import asyncio
import time
from contextlib import suppress
from datetime import datetime, timezone
from collections import deque
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.websocket.manager import manager
from app.services.vad import VADBuffer
from app.services.audio import convert_to_wav, decode_to_pcm, pcm_to_wav
from app.services.stt import transcribe_audio
from app.services.llm import generate_response, generate_response_stream
from app.services.tts import synthesize_speech, synthesize_speech_stream
from app.services.rag import retrieve_context
from app.services.sentences import split_sentences
from app.services.session import save_turn, end_session, create_session
from app.services.sentiment_analyzer import analyze_sentiment
from app.services.audio_processor import save_session_recording
from app.services.call_summarizer import generate_call_summary
from app.config import settings
from app.models.database import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter()

SESSION_LOG_MAX = 200
session_logs: dict[str, deque[dict]] = {}
session_log_events: dict[str, list[asyncio.Event]] = {}


async def _append_log(session_id: str, entry: dict) -> None:
    logs = session_logs.setdefault(session_id, deque(maxlen=SESSION_LOG_MAX))
    logs.append(entry)
    for ev in list(session_log_events.get(session_id, [])):
        ev.set()


async def _get_default_persona_id() -> str:
    supabase = get_supabase()
    try:
        res = supabase.table("personas").select("id").eq("name", "default").limit(1).execute()
        if res.data:
            return res.data[0]["id"]
    except Exception:
        pass
    try:
        res = supabase.table("personas").select("id").limit(1).execute()
        if res.data:
            return res.data[0]["id"]
    except Exception:
        pass
    return "default"


async def _stream_session_logs(session_id: str):
    ev = asyncio.Event()
    session_log_events.setdefault(session_id, []).append(ev)
    try:
        for entry in list(session_logs.get(session_id, [])):
            yield f"data: {json.dumps(entry)}\n\n"
        while True:
            await ev.wait()
            ev.clear()
            while session_logs.get(session_id):
                entry = session_logs[session_id].popleft()
                yield f"data: {json.dumps(entry)}\n\n"
    finally:
        session_log_events.get(session_id, []).remove(ev)


async def _stream_sentence_audio(session_id: str, sentence: str, voice_id: str, sentence_index: int):
    await manager.send_json(session_id, {"type": "status", "message": "speaking", "sentence_index": sentence_index})
    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS TTS sentence session={session_id} index={sentence_index} text={sentence}"})
    audio_buffer = bytearray()
    try:
        async for audio_chunk in synthesize_speech_stream(sentence, voice_id):
            audio_buffer.extend(audio_chunk)
    except asyncio.CancelledError:
        raise
    except asyncio.TimeoutError:
        await manager.send_json(session_id, {"type": "error", "message": "tts_timeout"})
        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS TTS timeout session={session_id} sentence={sentence_index}"})
        return
    except Exception as exc:
        await manager.send_json(session_id, {"type": "error", "message": f"tts_failed:{str(exc)}"})
        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS TTS failed session={session_id} sentence={sentence_index} error={exc}"})
        return
    if audio_buffer:
        await manager.send_bytes(session_id, bytes(audio_buffer))
    await manager.send_json(session_id, {"type": "sentence_end", "text": sentence, "index": sentence_index})
    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS sentence sent session={session_id} index={sentence_index} text={sentence}"})


async def _stream_response(session_id: str, conversation: list[dict[str, str]], voice_id: str, system_instruction: str = "You are a helpful voice assistant.", partial_response_ref: dict | None = None) -> tuple[str, bool]:
    await manager.send_json(session_id, {"type": "status", "message": "thinking"})
    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS LLM stream started session={session_id}"})

    full_response = ""
    if partial_response_ref is not None:
        partial_response_ref["text"] = ""
    tts_queue: asyncio.Queue[tuple[str, int] | None] = asyncio.Queue()
    sentences_sent = 0
    timeout_error = False
    worker: asyncio.Task | None = None

    async def tts_worker():
        nonlocal sentences_sent
        while True:
            item = await tts_queue.get()
            if item is None:
                break
            sentence, idx = item
            await _stream_sentence_audio(session_id, sentence, voice_id, idx)
            sentences_sent += 1
            tts_queue.task_done()

    try:
        worker = asyncio.create_task(tts_worker())
        async for chunk in generate_response_stream(conversation, system_instruction):
            full_response += chunk
            if partial_response_ref is not None:
                partial_response_ref["text"] = full_response
            sentences = await split_sentences(full_response)
            while len(sentences) > 1:
                sentence = sentences.pop(0)
                full_response = full_response[len(sentence):].lstrip()
                await tts_queue.put((sentence, sentences_sent))
    except asyncio.TimeoutError:
        timeout_error = True
        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS LLM timeout session={session_id}"})
        if not full_response:
            full_response = "I'm sorry, I'm taking too long to respond. Please try again."
    finally:
        if worker is not None:
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker
            with suppress(asyncio.CancelledError):
                while not tts_queue.empty():
                    tts_queue.get_nowait()

    if full_response.strip():
        await _stream_sentence_audio(session_id, full_response.strip(), voice_id, sentences_sent)
        sentences_sent += 1

    await manager.send_json(session_id, {"type": "status", "message": "response_ready"})
    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS response ready session={session_id} text={full_response} timeout={timeout_error}"})
    return full_response, timeout_error


async def _process_audio_chunk(session_id: str, chunk: bytes, vad: VADBuffer, conversation: list, db_session_id: str, voice_id: str, current_turn_task_ref: dict):
    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS audio chunk session={session_id} bytes={len(chunk)}"})
    await manager.send_json(session_id, {"type": "status", "message": "upload_received"})

    if current_turn_task_ref.get("task") and not current_turn_task_ref["task"].done():
        current_turn_task_ref["task"].cancel()
        try:
            await current_turn_task_ref["task"]
        except asyncio.CancelledError:
            await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS turn task cancelled session={session_id}"})
        current_turn_task_ref["task"] = None

    if not chunk.startswith(b"RIFF"):
        pcm_chunk = chunk
    else:
        try:
            pcm_chunk = decode_to_pcm(chunk, sample_rate=settings.audio_sample_rate)
        except Exception as exc:
            await manager.send_json(session_id, {"type": "error", "message": f"decode_failed:{str(exc)}"})
            await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS decode failed session={session_id} error={exc}"})
            return None

    await manager.send_json(session_id, {"type": "status", "message": "decoded"})
    vad_frame_ms = 30
    frame_size = int(settings.audio_sample_rate * 2 * (vad_frame_ms / 1000))
    await manager.send_json(session_id, {"type": "status", "message": "vading"})
    vad_frames = 0
    speech_ended = False
    audio_data = None
    pending_frames = bytearray()
    for i in range(0, len(pcm_chunk), frame_size):
        frame = bytes(pcm_chunk[i:i + frame_size])
        if len(frame) < frame_size:
            pending_frames.extend(frame)
            continue
        if pending_frames:
            frame = bytes(pending_frames) + frame
            pending_frames.clear()
            if len(frame) > frame_size:
                excess = bytes(frame[frame_size:])
                pending_frames.extend(excess)
                frame = bytes(frame[:frame_size])
        vad_frames += 1
        try:
            frame_audio, frame_speech_ended = vad.process(frame)
        except Exception as exc:
            await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS VAD error session={session_id} error={exc}"})
            continue
        if frame_audio:
            await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "debug", "msg": f"WS VAD session={session_id} speech_ended={frame_speech_ended} audio_len={len(frame_audio)}"})
        if frame_speech_ended and frame_audio:
            speech_ended = True
            audio_data = frame_audio
            break
        if vad_frames % 50 == 0:
            await manager.send_json(session_id, {"type": "status", "message": "vading"})

    if pending_frames:
        vad_frames += 1
        try:
            frame_audio, frame_speech_ended = vad.process(bytes(pending_frames))
            if frame_speech_ended and frame_audio:
                speech_ended = True
                audio_data = frame_audio
        except Exception as exc:
            await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS VAD error session={session_id} error={exc}"})

    if not speech_ended:
        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS VAD no speech end detected session={session_id} vad_frames={vad_frames} chunk_len={len(pcm_chunk)}"})
        if len(pcm_chunk) >= frame_size:
            audio_data = pcm_chunk
            speech_ended = True

    if speech_ended and audio_data:
        return audio_data
    return None


async def _process_transcript(session_id: str, user_text: str, conversation: list, db_session_id: str, voice_id: str, current_turn_task_ref: dict):
    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS transcript session={session_id} text={user_text}"})
    await manager.send_json(session_id, {"type": "transcript", "role": "user", "text": user_text, "timestamp": datetime.now(timezone.utc).isoformat()})
    conversation.append({"role": "user", "content": user_text})

    sentiment = "neutral"
    try:
        sentiment = await analyze_sentiment(user_text)
    except Exception:
        pass
    await manager.send_json(session_id, {"type": "sentiment", "label": sentiment})
    if sentiment == "frustrated":
        await manager.send_json(session_id, {"type": "alert", "level": "warning", "message": "Frustration detected! Escalating agent tone."})

    await save_turn(db_session_id, "user", user_text, sentiment=sentiment, latency_ms=0)

    await manager.send_json(session_id, {"type": "status", "message": "retrieving_context"})
    try:
        context = await asyncio.wait_for(retrieve_context(user_text), timeout=10)
    except asyncio.TimeoutError:
        context = []
        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS RAG timeout session={session_id}"})
    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS RAG context session={session_id} chunks={len(context) if context else 0}"})

    system_instruction = "You are a helpful voice assistant."
    if context:
        context_str = "\n".join([f"- {chunk}" for chunk in context])
        system_instruction += (
            "\n\nUse the following reference documents to answer the user's question:\n"
            f"{context_str}\n\n"
            "INSTRUCTION: Cite your sources naturally in spoken prose (for example, 'According to the uploaded agreement...'). "
            "Do NOT use markdown footnotes like [1] or formatted brackets."
        )

    turn_start = time.perf_counter()
    partial_response_container = {"text": ""}
    current_turn_task_ref["task"] = asyncio.create_task(_stream_response(session_id, conversation, voice_id, system_instruction, partial_response_container))
    try:
        response_text, _ = await asyncio.wait_for(current_turn_task_ref["task"], timeout=30)
    except asyncio.TimeoutError:
        await manager.send_json(session_id, {"type": "error", "message": "llm_timeout"})
        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS LLM timeout session={session_id}"})
        response_text = "I'm sorry, I'm taking too long to respond. Please try again."
    except asyncio.CancelledError:
        await manager.send_json(session_id, {"type": "status", "message": "interrupted"})
        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS turn cancelled session={session_id}"})
        partial_text = partial_response_container.get("text", "").strip()
        if partial_text:
            await save_turn(db_session_id, "assistant", partial_text + "...", interrupted=True)
        return None
    finally:
        current_turn_task_ref["task"] = None

    conversation.append({"role": "assistant", "content": response_text})
    latency_ms = int((time.perf_counter() - turn_start) * 1000)
    await manager.send_json(session_id, {"type": "transcript", "role": "assistant", "text": response_text, "timestamp": datetime.now(timezone.utc).isoformat()})
    await save_turn(db_session_id, "assistant", response_text, latency_ms=latency_ms, interrupted=False)
    return response_text


@router.websocket("/ws/voice/{session_id}")
async def websocket_voice(websocket: WebSocket, session_id: str):
    await manager.connect(session_id, websocket)
    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS connected session={session_id}"})

    persona_id = await _get_default_persona_id()
    db_session_id = await create_session(persona_id=persona_id, session_id=session_id)
    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS db session created session={session_id} db_session={db_session_id} persona={persona_id}"})

    vad = VADBuffer(sample_rate=settings.audio_sample_rate)
    conversation: list[dict[str, str]] = []
    voice_id = "en-IN-NeerjaNeural"
    is_playing = False
    filler_sent = False
    current_turn_task_ref: dict[str, asyncio.Task | None] = {"task": None}
    processing_lock = asyncio.Lock()
    message_queue: asyncio.Queue[dict | None] = asyncio.Queue()
    receiver_task: asyncio.Task | None = None
    audio_tasks: set[asyncio.Task] = set()
    session_audio_bytes = bytearray()
    MAX_CONCURRENT_AUDIO_TASKS = 2

    async def _receive_messages():
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=60.0)
                await message_queue.put(message)
            except asyncio.TimeoutError:
                await message_queue.put({"type": "ping"})
            except WebSocketDisconnect:
                await message_queue.put(None)
                break
            except RuntimeError as exc:
                await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS receive error session={session_id} error={exc}"})
                break

    async def _handle_audio_message(chunk: bytes):
        async with processing_lock:
            session_audio_bytes.extend(chunk)
            audio_data = await _process_audio_chunk(session_id, chunk, vad, conversation, db_session_id, voice_id, current_turn_task_ref)
            if audio_data:
                await manager.send_json(session_id, {"type": "status", "message": "processing"})
                await manager.send_json(session_id, {"type": "status", "message": "transcribing"})
                await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS speech ended session={session_id} audio_len={len(audio_data)}"})
                wav_audio = pcm_to_wav(audio_data, sample_rate=settings.audio_sample_rate)
                try:
                    user_text = await asyncio.wait_for(transcribe_audio(wav_audio), timeout=15)
                except asyncio.TimeoutError:
                    await manager.send_json(session_id, {"type": "error", "message": "stt_timeout"})
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS STT timeout session={session_id}"})
                    return
                await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS STT session={session_id} text={user_text}"})
                await manager.send_json(session_id, {"type": "status", "message": "transcribed"})
                if not user_text:
                    await manager.send_json(session_id, {"type": "error", "message": "empty_transcript"})
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS empty transcript session={session_id}"})
                    return
                await _process_transcript(session_id, user_text, conversation, db_session_id, voice_id, current_turn_task_ref)

    try:
        await manager.send_json(session_id, {"type": "status", "message": "connected"})
        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS status connected session={session_id}"})

        receiver_task = asyncio.create_task(_receive_messages())

        while True:
            message = await message_queue.get()
            if message is None:
                break
            await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "debug", "msg": f"WS receive session={session_id} message_keys={list(message.keys())}"})

            if "bytes" in message:
                if len(audio_tasks) >= MAX_CONCURRENT_AUDIO_TASKS:
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS audio task limit reached session={session_id}"})
                    continue
                task = asyncio.create_task(_handle_audio_message(message["bytes"]))
                audio_tasks.add(task)
                task.add_done_callback(audio_tasks.discard)
                await asyncio.sleep(0)

            elif "text" in message:
                data = json.loads(message["text"])
                msg_type = data.get("type")
                await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS text message session={session_id} type={msg_type}"})

                if msg_type == "auth":
                    persona_id = data.get("persona_id", persona_id)
                    voice_id = data.get("voice_id", voice_id)
                    await manager.send_json(session_id, {"type": "status", "message": "authenticated"})
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS authenticated session={session_id} persona={persona_id} voice={voice_id} db_session={db_session_id}"})

                elif msg_type == "voice_select":
                    voice_id = data.get("voice_id", voice_id)
                    await manager.send_json(session_id, {"type": "status", "message": f"voice_selected:{voice_id}"})
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS voice selected session={session_id} voice={voice_id}"})

                elif msg_type == "stop_playback":
                    is_playing = False
                    if current_turn_task_ref.get("task") and not current_turn_task_ref["task"].done():
                        current_turn_task_ref["task"].cancel()
                        try:
                            await current_turn_task_ref["task"]
                        except asyncio.CancelledError:
                            pass
                        current_turn_task_ref["task"] = None
                    await manager.send_json(session_id, {"type": "status", "message": "playback_stopped"})
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS playback stopped session={session_id}"})

                elif msg_type == "transcript":
                    user_text = data.get("text", "")
                    if not user_text:
                        continue
                    await _process_transcript(session_id, user_text, conversation, db_session_id, voice_id, current_turn_task_ref)

    except WebSocketDisconnect:
        pass
    finally:
        for task in list(audio_tasks):
            task.cancel()
        for task in list(audio_tasks):
            with suppress(asyncio.CancelledError):
                await task
        if receiver_task:
            receiver_task.cancel()
            try:
                await receiver_task
            except asyncio.CancelledError:
                pass
        if current_turn_task_ref.get("task") and not current_turn_task_ref["task"].done():
            current_turn_task_ref["task"].cancel()
            try:
                await current_turn_task_ref["task"]
            except asyncio.CancelledError:
                pass

        recording_url = None
        if session_audio_bytes:
            try:
                recording_url = await save_session_recording(db_session_id, bytes(session_audio_bytes))
            except Exception:
                pass

        summary = ""
        if conversation:
            try:
                summary = await generate_call_summary(conversation)
            except Exception:
                pass

        await end_session(db_session_id, recording_url=recording_url, summary=summary or None)
        manager.disconnect(session_id)
        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS disconnected session={session_id} target_session={db_session_id}"})