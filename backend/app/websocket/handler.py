import json
import logging
import asyncio
import time
import uuid
import math
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
from app.models.database import get_supabase, run_supabase

logger = logging.getLogger(__name__)
router = APIRouter()
MAX_CONCURRENT_AUDIO_TASKS = settings.ws_max_concurrent_audio_tasks
CHUNK_RMS_SILENCE_THRESHOLD = 120


async def _log_stage(session_id: str, stage: str, level: str = "info", **extra) -> None:
    msg_parts = [f"STAGE: {stage}"]
    if extra:
        msg_parts.append(" ".join(f"{k}={v}" for k, v in extra.items()))
    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": level, "msg": " ".join(msg_parts)})


async def _load_session(session_id: str) -> dict | None:
    client = get_supabase()
    try:
        res = await run_supabase(lambda: client.table("sessions").select("*").eq("id", session_id).limit(1).execute())
        if res.data:
            return res.data[0]
    except Exception:
        pass
    return None


def _is_duplicate_turn(conversation_mgr: ConversationManager, speaker: str, text: str) -> bool:
    history = conversation_mgr.get_history()
    if not history:
        return False
    last = history[-1]
    return last.get("role") == speaker and last.get("content") == text


def _chunk_rms(chunk: bytes) -> int:
    if len(chunk) % 2 != 0:
        return 0
    samples = memoryview(chunk).cast("h")
    if not samples:
        return 0
    sum_sq = 0
    for s in samples:
        sum_sq += s * s
    return int(math.sqrt(sum_sq / len(samples)))


async def _process_audio_chunk(
    session_id: str,
    chunk: bytes,
    vad: VADBuffer,
    heartbeat_state: dict | None = None,
) -> tuple[bytes | None, bool]:
    await _log_stage(session_id, "AUDIO_RECEIVED", bytes=len(chunk), chunk_prefix=chunk[:8].hex())
    await manager.send_json(session_id, {"type": "status", "message": "upload_received"})

    if heartbeat_state is not None:
        heartbeat_state["consecutive_failures"] = 0

    is_silent = await asyncio.to_thread(
        lambda: len(chunk) >= 4 and _chunk_rms(chunk) < CHUNK_RMS_SILENCE_THRESHOLD
    )
    if is_silent:
        return None, False

    try:
        pcm_chunk = await asyncio.to_thread(decode_to_pcm, chunk, settings.audio_sample_rate)
    except Exception as exc:
        if chunk.startswith(b"RIFF") or chunk.startswith(b"WAVE"):
            await manager.send_json(session_id, {"type": "error", "message": f"decode_failed:{str(exc)}"})
            await _log_stage(session_id, "AUDIO_DECODE_FAILED", level="error", error=str(exc))
            return None, False
        pcm_chunk = chunk
        await _log_stage(session_id, "AUDIO_ASSUMED_RAW_PCM", bytes=len(chunk))

    await manager.send_json(session_id, {"type": "status", "message": "decoded"})
    vad_frame_ms = 32
    frame_size = int(settings.audio_sample_rate * 2 * (vad_frame_ms / 1000))
    await manager.send_json(session_id, {"type": "status", "message": "vading"})

    vad_before_triggered = vad.triggered
    vad_frames = 0
    speech_ended = False
    audio_data = None

    try:
        frame_audio, frame_speech_ended = await asyncio.to_thread(vad.process_bytes, pcm_chunk, frame_size)
        if frame_audio:
            await _append_log(
                session_id,
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "level": "debug",
                    "msg": f"WS VAD session={session_id} speech_ended={frame_speech_ended} audio_len={len(frame_audio)}",
                },
            )
        elif settings.vad_threshold is not None:
            await _append_log(
                session_id,
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "level": "debug",
                    "msg": f"WS VAD session={session_id} speech_ended={frame_speech_ended} audio_len=0",
                },
            )
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


async def _partial_stt_loop(
    session_id: str,
    vad: VADBuffer,
    session_audio_bytes: AudioBuffer,
    stop_event: asyncio.Event,
    state: dict,
):
    while not stop_event.is_set():
        await asyncio.sleep(0.5)
        if stop_event.is_set():
            break
        if not vad.triggered:
            state["speech_started_time"] = 0.0
            continue
        now = time.perf_counter()
        if state["speech_started_time"] == 0.0:
            state["speech_started_time"] = now
        if now - state["speech_started_time"] < 1.0:
            continue
        if state["partial_stt_in_progress"]:
            continue
        if (now - state["last_partial_stt_time"]) < 1.5:
            continue
        recent_bytes = session_audio_bytes.get_recent_bytes(max_bytes=settings.audio_sample_rate * 2 * 5)
        if len(recent_bytes) < settings.audio_sample_rate * 2 * 1:
            continue
        state["partial_stt_in_progress"] = True
        try:
            wav_audio = await asyncio.to_thread(pcm_to_wav, recent_bytes, sample_rate=settings.audio_sample_rate)
            text = await asyncio.wait_for(transcribe_audio(wav_audio), timeout=10)
            if text and not is_noisy_transcription(text):
                await manager.send_json(session_id, {"type": "partial_transcript", "role": "user", "text": text})
                state["last_partial_stt_time"] = now
        except Exception:
            pass
        finally:
            state["partial_stt_in_progress"] = False


@router.websocket("/ws/voice/{session_id}")
async def websocket_voice(websocket: WebSocket, session_id: str):
    await manager.connect(session_id, websocket)
    await _log_stage(session_id, "CONNECTION_ESTABLISHED")

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
        await _log_stage(session_id, "SESSION_INIT_FAILED", level="error", error=str(exc))
        try:
            await manager.send_json(session_id, {"type": "error", "message": f"session_init_failed:{type(exc).__name__}"})
        except Exception:
            pass
        manager.disconnect(session_id)
        return

    await _log_stage(session_id, "SESSION_INITIALIZED", db_session=db_session_id, persona=persona_id)

    manager.enable_recording(session_id)
    await _log_stage(session_id, "RECORDING_ENABLED")

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
    heartbeat_state: dict[str, int] = {"consecutive_failures": 0}
    heartbeat_task: asyncio.Task | None = None
    current_user_message_id: str | None = None
    recording_start_time: float | None = None
    partial_stt_state = {
        "speech_started_time": 0.0,
        "last_partial_stt_time": 0.0,
        "partial_stt_in_progress": False,
    }
    partial_stt_stop = asyncio.Event()
    partial_stt_task = asyncio.create_task(
        _partial_stt_loop(session_id, vad, session_audio_bytes, partial_stt_stop, partial_stt_state)
    )

    response_queue: asyncio.Queue[dict | None] = asyncio.Queue()

    async def _response_worker():
        while True:
            try:
                request = await response_queue.get()
            except asyncio.CancelledError:
                break
            if request is None:
                break
            try:
                if current_turn_task_ref.get("task") and not current_turn_task_ref["task"].done():
                    if request.get("force"):
                        current_turn_task_ref["task"].cancel()
                        try:
                            await current_turn_task_ref["task"]
                        except asyncio.CancelledError:
                            pass
                        current_turn_task_ref["task"] = None
                    else:
                        continue
                current_turn_task_ref["task"] = asyncio.create_task(
                    start_turn_with_filler(
                        session_id=request["session_id"],
                        user_text=request["user_text"],
                        conversation_mgr=request["conversation_mgr"],
                        voice_id=request["voice_id"],
                        persona_id=request["persona_id"],
                        db_session_id=request["db_session_id"],
                        stt_latency_ms=request.get("stt_latency_ms"),
                        filler_threshold_ms=request.get("filler_threshold_ms", settings.filler_threshold_ms),
                        user_message_id=request.get("user_message_id"),
                    )
                )

                async def _safe_on_done(fut):
                    try:
                        await _on_turn_done(fut)
                    except Exception:
                        pass

                current_turn_task_ref["task"].add_done_callback(lambda fut: asyncio.create_task(_safe_on_done(fut)))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS response worker error session={session_id} error={exc}"})

    response_task = asyncio.create_task(_response_worker())

    async def _heartbeat():
        max_failures = 5
        while True:
            await asyncio.sleep(settings.ws_heartbeat_interval_s)
            try:
                await websocket.send_ping()
                heartbeat_state["consecutive_failures"] = 0
            except Exception:
                heartbeat_state["consecutive_failures"] += 1
                await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS heartbeat failed session={session_id} failures={heartbeat_state['consecutive_failures']}"})
                if heartbeat_state["consecutive_failures"] >= max_failures:
                    await message_queue.put(None)
                    break

    async def _receive_messages():
        consecutive_timeouts = 0
        max_timeouts = 2
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=settings.ws_receive_timeout_s)
                consecutive_timeouts = 0
                await message_queue.put(message)
            except asyncio.TimeoutError:
                consecutive_timeouts += 1
                try:
                    await websocket.send_ping()
                except Exception:
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS stale connection detected session={session_id} timeouts={consecutive_timeouts}"})
                    await message_queue.put(None)
                    break
                if consecutive_timeouts >= max_timeouts:
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS stale connection session={session_id}"})
                    await message_queue.put(None)
                    break
            except WebSocketDisconnect:
                await message_queue.put(None)
                break
            except asyncio.CancelledError:
                await message_queue.put(None)
                break
            except RuntimeError as exc:
                await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS receive error session={session_id} error={exc}"})
                await message_queue.put(None)
                break
            except Exception as exc:
                await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS receive unexpected error session={session_id} error={exc}"})
                await message_queue.put(None)
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

    async def _cancel_pending_audio_tasks():
        for task in list(audio_tasks):
            if not task.done():
                task.cancel()
        for task in list(audio_tasks):
            with suppress(asyncio.CancelledError):
                await task
        audio_tasks.clear()

    async def _on_turn_done(fut):
        nonlocal current_user_message_id, recording_start_time
        try:
            result = fut.result()
        except asyncio.CancelledError:
            recording_start_time = None
            return
        except Exception:
            recording_start_time = None
            return
        if current_user_message_id and recording_start_time:
            end_ms = int((time.perf_counter() - recording_start_time) * 1000)
            try:
                await run_supabase(
                    lambda: get_supabase().table("messages").update({"recording_end_ms": end_ms}).eq("id", current_user_message_id).execute()
                )
            except Exception:
                pass
        recording_start_time = None

    async def _handle_audio_message(chunk: bytes):
        nonlocal filler_sent, current_user_message_id, recording_start_time
        try:
            async with processing_lock:
                session_audio_bytes.append(chunk)
                audio_data, speech_started = await _process_audio_chunk(session_id, chunk, vad, heartbeat_state)

                if speech_started and current_turn_task_ref.get("task") and not current_turn_task_ref["task"].done():
                    await _cancel_current_turn()
                    await manager.send_json(session_id, {"type": "status", "message": "interrupted"})
                    await _append_log(
                        session_id,
                        {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS interrupted by user session={session_id}"},
                    )

                if not audio_data:
                    return

                partial_stt_state["speech_started_time"] = 0.0

                if current_turn_task_ref.get("task") and not current_turn_task_ref["task"].done():
                    return

                await manager.send_json(session_id, {"type": "status", "message": "processing"})
                await manager.send_json(session_id, {"type": "status", "message": "transcribing"})
                await _append_log(
                    session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS speech ended session={session_id} audio_len={len(audio_data)}"}
                )
                wav_audio = await asyncio.to_thread(pcm_to_wav, audio_data, sample_rate=settings.audio_sample_rate)
                try:
                    stt_start = time.perf_counter()
                    user_text = await asyncio.wait_for(transcribe_audio(wav_audio), timeout=15)
                    stt_latency_ms = int((time.perf_counter() - stt_start) * 1000)
                except asyncio.TimeoutError:
                    await manager.send_json(session_id, {"type": "error", "message": "stt_timeout"})
                    await manager.send_json(session_id, {"type": "status", "message": "idle"})
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS STT timeout session={session_id}"})
                    return
                await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS STT session={session_id} text={user_text} latency_ms={stt_latency_ms}"})
                await manager.send_json(session_id, {"type": "status", "message": "transcribed"})
                if not user_text or is_noisy_transcription(user_text):
                    await manager.send_json(session_id, {"type": "error", "message": "empty_transcript"})
                    await manager.send_json(session_id, {"type": "status", "message": "idle"})
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS empty transcript session={session_id}"})
                    return

                if _is_duplicate_turn(conversation_mgr, "user", user_text):
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS duplicate transcript skipped session={session_id} text={user_text}"})
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

                await response_queue.put({
                    "session_id": session_id,
                    "user_text": user_text,
                    "conversation_mgr": conversation_mgr,
                    "voice_id": voice_id,
                    "persona_id": persona_id,
                    "db_session_id": db_session_id,
                    "stt_latency_ms": stt_latency_ms,
                    "filler_threshold_ms": settings.filler_threshold_ms,
                    "user_message_id": current_user_message_id,
                    "force": False,
                })
        except Exception as exc:
            await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS audio task error session={session_id} error={exc}"})

    async def _handle_control_message(data: dict):
        nonlocal filler_sent, current_user_message_id, recording_start_time, persona_id, voice_id
        try:
            msg_type = data.get("type")
            if msg_type == "auth":
                persona_id = await resolve_persona_id(data.get("persona_id", persona_id))
                voice_id = data.get("voice_id") or voice_id
                await manager.send_json(session_id, {"type": "status", "message": "authenticated"})
                await _append_log(
                    session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS authenticated session={session_id} persona={persona_id} voice={voice_id} db_session={db_session_id}"}
                )

            elif msg_type == "voice_select":
                voice_id = data.get("voice_id") or voice_id
                await manager.send_json(session_id, {"type": "status", "message": f"voice_selected:{voice_id}"})
                await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS voice selected session={session_id} voice={voice_id}"})
                try:
                    await run_supabase(
                        lambda: get_supabase().table("sessions").update({"selected_voice": voice_id}).eq("id", db_session_id).execute()
                    )
                except Exception:
                    pass

            elif msg_type == "stop_playback":
                await _cancel_current_turn()
                await manager.send_json(session_id, {"type": "status", "message": "playback_stopped"})
                await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS playback stopped session={session_id}"})

            elif msg_type == "stop_listening":
                await _cancel_pending_audio_tasks()
                await manager.send_json(session_id, {"type": "status", "message": "processing"})
                await manager.send_json(session_id, {"type": "status", "message": "transcribing"})
                async with processing_lock:
                    audio_data = await asyncio.to_thread(vad.flush)
                if not audio_data:
                    fallback_bytes = session_audio_bytes.get_recent_bytes(settings.audio_sample_rate * 2 * 3)
                    if len(fallback_bytes) >= settings.audio_sample_rate * 2 * 1:
                        audio_data = fallback_bytes
                        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS VAD fallback session={session_id} audio_len={len(audio_data)}"})
                    else:
                        await manager.send_json(session_id, {"type": "status", "message": "idle"})
                        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS flush empty session={session_id}"})
                        session_audio_bytes.clear()
                        return
                session_audio_bytes.clear()
                await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS flush session={session_id} audio_len={len(audio_data)}"})
                wav_audio = await asyncio.to_thread(pcm_to_wav, audio_data, sample_rate=settings.audio_sample_rate)
                try:
                    stt_start = time.perf_counter()
                    user_text = await asyncio.wait_for(transcribe_audio(wav_audio), timeout=15)
                    stt_latency_ms = int((time.perf_counter() - stt_start) * 1000)
                except asyncio.TimeoutError:
                    await manager.send_json(session_id, {"type": "error", "message": "stt_timeout"})
                    await manager.send_json(session_id, {"type": "status", "message": "idle"})
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS STT timeout session={session_id}"})
                    return
                await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS STT session={session_id} text={user_text} latency_ms={stt_latency_ms}"})
                await manager.send_json(session_id, {"type": "status", "message": "transcribed"})
                if not user_text or is_noisy_transcription(user_text):
                    await manager.send_json(session_id, {"type": "error", "message": "empty_transcript"})
                    await manager.send_json(session_id, {"type": "status", "message": "idle"})
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS empty transcript session={session_id}"})
                    return
                await manager.send_json(session_id, {"type": "transcript", "role": "user", "text": user_text})
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
                await response_queue.put({
                    "session_id": session_id,
                    "user_text": user_text,
                    "conversation_mgr": conversation_mgr,
                    "voice_id": voice_id,
                    "persona_id": persona_id,
                    "db_session_id": db_session_id,
                    "stt_latency_ms": stt_latency_ms,
                    "filler_threshold_ms": settings.filler_threshold_ms,
                    "user_message_id": current_user_message_id,
                    "force": True,
                })

            elif msg_type == "transcript":
                if data.get("role") != "user":
                    return
                user_text = data.get("text", "")
                if not user_text:
                    return
                if _is_duplicate_turn(conversation_mgr, "user", user_text):
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS duplicate transcript skipped session={session_id} text={user_text}"})
                    return
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
                await response_queue.put({
                    "session_id": session_id,
                    "user_text": user_text,
                    "conversation_mgr": conversation_mgr,
                    "voice_id": voice_id,
                    "persona_id": persona_id,
                    "db_session_id": db_session_id,
                    "stt_latency_ms": None,
                    "filler_threshold_ms": settings.filler_threshold_ms,
                    "user_message_id": current_user_message_id,
                    "force": True,
                })
        except Exception as exc:
            await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS control task error session={session_id} error={exc}"})

    try:
        await manager.send_json(session_id, {"type": "status", "message": "connected"})
        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS status connected session={session_id}"})

        receiver_task = asyncio.create_task(_receive_messages())
        heartbeat_task = asyncio.create_task(_heartbeat())

        while True:
            message = await message_queue.get()
            if message is None:
                break

            if "bytes" in message:
                try:
                    if len(audio_tasks) >= MAX_CONCURRENT_AUDIO_TASKS:
                        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS audio task limit reached session={session_id}"})
                        continue
                    task = asyncio.create_task(_handle_audio_message(message["bytes"]))
                    audio_tasks.add(task)
                    task.add_done_callback(audio_tasks.discard)
                except Exception as exc:
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS audio dispatch error session={session_id} error={exc}"})

            elif "text" in message:
                try:
                    data = json.loads(message["text"])
                    msg_type = data.get("type")

                    if msg_type == "ping":
                        try:
                            await websocket.send_text(json.dumps({"type": "pong"}))
                        except Exception:
                            await message_queue.put(None)
                        continue

                    if msg_type == "stop_call":
                        await _cancel_current_turn()
                        await manager.send_json(session_id, {"type": "status", "message": "call_ended"})
                        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS call ended session={session_id}"})
                        try:
                            await websocket.close()
                        except Exception:
                            pass
                        await message_queue.put(None)
                        break

                    task = asyncio.create_task(_handle_control_message(data))
                except Exception as exc:
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS text dispatch error session={session_id} error={exc}"})

            await asyncio.sleep(0)

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

        if response_task:
            response_task.cancel()
            with suppress(asyncio.CancelledError):
                await response_task

        partial_stt_stop.set()
        with suppress(asyncio.CancelledError):
            await partial_stt_task

        recording_url = None
        try:
            user_pcm = session_audio_bytes.get_bytes()
            ai_segments = manager.get_ai_segments(session_id)
            if user_pcm or ai_segments:
                composed = await asyncio.to_thread(compose_call_recording, user_pcm, ai_segments, sample_rate=settings.audio_sample_rate)
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
        current_ws = manager.active_connections.get(session_id)
        if current_ws is None or current_ws is websocket:
            manager.disconnect(session_id)
        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS disconnected session={session_id} target_session={db_session_id}"})
        from app.services.call_session_logger import close_session
        await close_session(session_id)
