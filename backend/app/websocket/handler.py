import json
import logging
import asyncio
import time
import uuid
from contextlib import suppress
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.websocket.manager import manager, _append_log
from app.services.vad import VADBuffer
from app.services.audio_processor import decode_to_pcm, pcm_to_wav, compose_call_recording
from app.services.stt import transcribe_audio, is_noisy_transcription
from app.services.conversation_mgr import ConversationManager
from app.services.voice_pipeline import start_turn_with_filler
from app.websocket.audio_buffer import AudioBuffer
from app.services.call_summarizer import generate_call_summary
from app.services.session import create_session, end_session, resolve_persona_id, _get_default_persona_id, save_turn
from app.services.tts import get_persona_voice_id
from app.config import settings
from app.models.database import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter()
MAX_CONCURRENT_AUDIO_TASKS = settings.ws_max_concurrent_audio_tasks


async def _load_session(session_id: str) -> dict | None:
    supabase = get_supabase()
    try:
        res = supabase.table("sessions").select("*").eq("id", session_id).limit(1).execute()
        if res.data:
            return res.data[0]
    except Exception:
        pass
    return None


async def _process_audio_chunk(
    session_id: str,
    chunk: bytes,
    vad: VADBuffer,
) -> tuple[bytes | None, bool]:
    await _append_log(
        session_id,
        {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS audio chunk session={session_id} bytes={len(chunk)}"},
    )
    await manager.send_json(session_id, {"type": "status", "message": "upload_received"})

    if not chunk.startswith(b"RIFF"):
        pcm_chunk = chunk
    else:
        try:
            pcm_chunk = decode_to_pcm(chunk, sample_rate=settings.audio_sample_rate)
        except Exception as exc:
            await manager.send_json(session_id, {"type": "error", "message": f"decode_failed:{str(exc)}"})
            await _append_log(
                session_id,
                {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS decode failed session={session_id} error={exc}"},
            )
            return None, False

    await manager.send_json(session_id, {"type": "status", "message": "decoded"})
    vad_frame_ms = 30
    frame_size = int(settings.audio_sample_rate * 2 * (vad_frame_ms / 1000))
    await manager.send_json(session_id, {"type": "status", "message": "vading"})

    vad_before_triggered = vad.triggered
    vad_frames = 0
    speech_ended = False
    audio_data = None
    pending_frames = bytearray()

    for i in range(0, len(pcm_chunk), frame_size):
        frame = bytes(pcm_chunk[i : i + frame_size])
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
            await _append_log(
                session_id,
                {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS VAD error session={session_id} error={exc}"},
            )
            continue
        if frame_audio:
            await _append_log(
                session_id,
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "level": "debug",
                    "msg": f"WS VAD session={session_id} speech_ended={frame_speech_ended} audio_len={len(frame_audio)}",
                },
            )
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
            await _append_log(
                session_id,
                {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS VAD error session={session_id} error={exc}"},
            )

    vad_after_triggered = vad.triggered
    speech_started = (not vad_before_triggered) and vad_after_triggered

    if not speech_ended:
        return None, speech_started

    if speech_ended and audio_data:
        return audio_data, speech_started
    return None, speech_started


@router.websocket("/ws/voice/{session_id}")
async def websocket_voice(websocket: WebSocket, session_id: str):
    await manager.connect(session_id, websocket)
    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS connected session={session_id}"})

    try:
        persona_id = await _get_default_persona_id()
        anonymous_user_id = str(uuid.uuid4())
        db_session_id = await create_session(persona_id=persona_id, user_id=anonymous_user_id, session_id=session_id)
        existing_session = await _load_session(db_session_id)
        voice_id = "en-IN-NeerjaNeural"
        if existing_session and existing_session.get("selected_voice"):
            voice_id = existing_session["selected_voice"]
        else:
            try:
                voice_id = await get_persona_voice_id(persona_id)
            except Exception:
                pass
    except Exception as exc:
        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS session init failed session={session_id} error={exc}"})
        try:
            await manager.send_json(session_id, {"type": "error", "message": f"session_init_failed:{type(exc).__name__}"})
        except Exception:
            pass
        manager.disconnect(session_id)
        return

    await _append_log(
        session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS db session created session={session_id} db_session={db_session_id} persona={persona_id}"}
    )

    manager.enable_recording(session_id)

    vad = VADBuffer(sample_rate=settings.audio_sample_rate)
    conversation_mgr = ConversationManager()
    if existing_session:
        try:
            await conversation_mgr.load_from_db(db_session_id)
        except Exception:
            pass

    filler_sent = False
    current_turn_task_ref: dict[str, asyncio.Task | None] = {"task": None}
    processing_lock = asyncio.Lock()
    message_queue: asyncio.Queue[dict | None] = asyncio.Queue()
    receiver_task: asyncio.Task | None = None
    audio_tasks: set[asyncio.Task] = set()
    session_audio_bytes = AudioBuffer()
    heartbeat_task: asyncio.Task | None = None
    current_user_message_id: str | None = None
    recording_start_time: float | None = None

    async def _heartbeat():
        while True:
            await asyncio.sleep(settings.ws_heartbeat_interval_s)
            try:
                await websocket.send_ping()
            except Exception:
                await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS heartbeat failed session={session_id}"})
                await message_queue.put(None)
                break

    async def _receive_messages():
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=settings.ws_receive_timeout_s)
                await message_queue.put(message)
            except asyncio.TimeoutError:
                try:
                    await websocket.send_ping()
                except Exception:
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS stale connection detected session={session_id}"})
                    await message_queue.put(None)
                    break
            except WebSocketDisconnect:
                await message_queue.put(None)
                break
            except asyncio.CancelledError:
                break
            except RuntimeError as exc:
                await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS receive error session={session_id} error={exc}"})
                break
            except Exception as exc:
                await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS receive unexpected error session={session_id} error={exc}"})
                break

    async def _cancel_current_turn():
        nonlocal filler_sent
        if current_turn_task_ref.get("task") and not current_turn_task_ref["task"].done():
            current_turn_task_ref["task"].cancel()
            try:
                await current_turn_task_ref["task"]
            except asyncio.CancelledError:
                pass
            current_turn_task_ref["task"] = None
        filler_sent = False

    def _on_turn_done(fut):
        nonlocal current_user_message_id
        try:
            result = fut.result()
        except asyncio.CancelledError:
            return
        except Exception:
            return
        if current_user_message_id and recording_start_time:
            end_ms = int((time.perf_counter() - recording_start_time) * 1000)
            supabase = get_supabase()
            try:
                supabase.table("messages").update({"recording_end_ms": end_ms}).eq("id", current_user_message_id).execute()
            except Exception:
                pass

    async def _handle_audio_message(chunk: bytes):
        nonlocal filler_sent, current_user_message_id, recording_start_time
        async with processing_lock:
            session_audio_bytes.append(chunk)
            audio_data, speech_started = await _process_audio_chunk(session_id, chunk, vad)

            if speech_started and current_turn_task_ref.get("task") and not current_turn_task_ref["task"].done():
                await _cancel_current_turn()
                await manager.send_json(session_id, {"type": "status", "message": "interrupted"})
                await _append_log(
                    session_id,
                    {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS interrupted by user session={session_id}"},
                )

            if not audio_data:
                return

            if current_turn_task_ref.get("task") and not current_turn_task_ref["task"].done():
                return

            await manager.send_json(session_id, {"type": "status", "message": "processing"})
            await manager.send_json(session_id, {"type": "status", "message": "transcribing"})
            await _append_log(
                session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS speech ended session={session_id} audio_len={len(audio_data)}"}
            )
            wav_audio = pcm_to_wav(audio_data, sample_rate=settings.audio_sample_rate)
            try:
                stt_start = time.perf_counter()
                user_text = await asyncio.wait_for(transcribe_audio(wav_audio), timeout=15)
                stt_latency_ms = int((time.perf_counter() - stt_start) * 1000)
            except asyncio.TimeoutError:
                await manager.send_json(session_id, {"type": "error", "message": "stt_timeout"})
                await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS STT timeout session={session_id}"})
                return
            await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS STT session={session_id} text={user_text} latency_ms={stt_latency_ms}"})
            await manager.send_json(session_id, {"type": "status", "message": "transcribed"})
            if not user_text or is_noisy_transcription(user_text):
                await manager.send_json(session_id, {"type": "error", "message": "empty_transcript"})
                await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS empty transcript session={session_id}"})
                return

            await manager.send_json(session_id, {"type": "transcript", "role": "user", "text": user_text})

            filler_sent = False
            if recording_start_time is None:
                recording_start_time = time.perf_counter()
            user_recording_start_ms = int((time.perf_counter() - recording_start_time) * 1000)
            current_user_message_id = await save_turn(
                db_session_id,
                "user",
                user_text,
                latency_ms=0,
                stt_latency_ms=stt_latency_ms,
                recording_start_ms=user_recording_start_ms,
            )

            current_turn_task_ref["task"] = asyncio.create_task(
                start_turn_with_filler(
                    session_id,
                    user_text,
                    conversation_mgr,
                    voice_id,
                    persona_id,
                    db_session_id,
                    stt_latency_ms=stt_latency_ms,
                    filler_threshold_ms=settings.filler_threshold_ms,
                )
            )
            current_turn_task_ref["task"].add_done_callback(_on_turn_done)

    try:
        await manager.send_json(session_id, {"type": "status", "message": "connected"})
        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS status connected session={session_id}"})

        receiver_task = asyncio.create_task(_receive_messages())
        heartbeat_task = asyncio.create_task(_heartbeat())

        while True:
            message = await message_queue.get()
            if message is None:
                break
            await _append_log(
                session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "debug", "msg": f"WS receive session={session_id} message_keys={list(message.keys())}"}
            )

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
                    persona_id = await resolve_persona_id(data.get("persona_id", persona_id))
                    voice_id = data.get("voice_id", voice_id)
                    await manager.send_json(session_id, {"type": "status", "message": "authenticated"})
                    await _append_log(
                        session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS authenticated session={session_id} persona={persona_id} voice={voice_id} db_session={db_session_id}"}
                    )

                elif msg_type == "voice_select":
                    voice_id = data.get("voice_id", voice_id)
                    await manager.send_json(session_id, {"type": "status", "message": f"voice_selected:{voice_id}"})
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS voice selected session={session_id} voice={voice_id}"})
                    try:
                        supabase = get_supabase()
                        supabase.table("sessions").update({"selected_voice": voice_id}).eq("id", db_session_id).execute()
                    except Exception:
                        pass

                elif msg_type == "stop_call":
                    await _cancel_current_turn()
                    await manager.send_json(session_id, {"type": "status", "message": "call_ended"})
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS call ended session={session_id}"})
                    break

                elif msg_type == "stop_playback":
                    await _cancel_current_turn()
                    await manager.send_json(session_id, {"type": "status", "message": "playback_stopped"})
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS playback stopped session={session_id}"})

                elif msg_type == "transcript":
                    user_text = data.get("text", "")
                    if not user_text:
                        continue
                    await _cancel_current_turn()
                    await manager.send_json(session_id, {"type": "transcript", "role": "user", "text": user_text})
                    if recording_start_time is None:
                        recording_start_time = time.perf_counter()
                    user_recording_start_ms = int((time.perf_counter() - recording_start_time) * 1000)
                    current_user_message_id = await save_turn(
                        db_session_id,
                        "user",
                        user_text,
                        latency_ms=0,
                        recording_start_ms=user_recording_start_ms,
                    )
                    current_turn_task_ref["task"] = asyncio.create_task(
                        start_turn_with_filler(
                            session_id,
                            user_text,
                            conversation_mgr,
                            voice_id,
                            persona_id,
                            db_session_id,
                            stt_latency_ms=None,
                            filler_threshold_ms=settings.filler_threshold_ms,
                        )
                    )
                    current_turn_task_ref["task"].add_done_callback(_on_turn_done)
                    try:
                        await asyncio.wait_for(current_turn_task_ref["task"], timeout=30)
                    except asyncio.TimeoutError:
                        await manager.send_json(session_id, {"type": "error", "message": "llm_timeout"})
                        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS LLM timeout session={session_id}"})
                    except asyncio.CancelledError:
                        pass
                    except Exception as exc:
                        await manager.send_json(session_id, {"type": "error", "message": f"turn_failed:{type(exc).__name__}"})
                        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS turn failed session={session_id} error={exc}"})

                elif msg_type == "ping":
                    try:
                        await websocket.send_text(json.dumps({"type": "pong"}))
                    except Exception:
                        break

    except WebSocketDisconnect:
        pass
    finally:
        if heartbeat_task:
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat_task
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
        await _cancel_current_turn()

        recording_url = None
        try:
            user_pcm = session_audio_bytes.get_bytes()
            ai_segments = manager.get_ai_segments(session_id)
            if user_pcm or ai_segments:
                composed = compose_call_recording(user_pcm, ai_segments, sample_rate=settings.audio_sample_rate)
                if composed:
                    recording_url = await save_session_recording(db_session_id, composed)
        except Exception:
            pass

        summary = ""
        if len(conversation_mgr) > 0:
            try:
                summary = await generate_call_summary(conversation_mgr.get_history())
            except Exception:
                pass

        await end_session(db_session_id, recording_url=recording_url, summary=summary or None)
        manager.disconnect(session_id)
        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS disconnected session={session_id} target_session={db_session_id}"})
