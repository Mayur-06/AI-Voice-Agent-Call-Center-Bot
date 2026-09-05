import json
import logging
import asyncio
import time
import uuid
from collections import defaultdict
from contextlib import suppress
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket
from app.websocket.manager import manager, _append_log
from app.services.vad import VADBuffer
from app.services.audio_processor import pcm_to_wav, compose_call_recording, save_session_recording
from app.services.stt import transcribe_audio, is_noisy_transcription
from app.services.conversation_mgr import ConversationManager
from app.services.call_summarizer import generate_call_summary
from app.services.session import create_session, end_session, _get_default_persona_id
from app.services.tts import get_persona_voice_id
from app.models.database import get_supabase, run_supabase
from app.config import settings
from app.orchestration.pipeline import SessionPipelineState, FiveQueuePipeline, safe_put_nowait, make_event, TextInMessage

logger = logging.getLogger(__name__)
router = APIRouter()

_session_handler_tasks: dict[str, asyncio.Task] = {}
_session_handler_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


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


@router.websocket("/ws/voice/{session_id}")
async def websocket_voice(websocket: WebSocket, session_id: str):
    async with _session_handler_locks[session_id]:
        existing_task = _session_handler_tasks.get(session_id)
        if existing_task is not None and existing_task.done():
            del _session_handler_tasks[session_id]
            existing_task = None

        if existing_task is not None and not existing_task.done():
            try:
                await websocket.accept()
                await websocket.send_json({"type": "info", "message": "session_already_active"})
                await websocket.close()
            except Exception:
                pass
            return

        await manager.connect(session_id, websocket)
        await _log_stage(session_id, "CONNECTION_ESTABLISHED")

        handler_task = asyncio.create_task(_handle_voice_pipeline_v2(websocket, session_id))
        _session_handler_tasks[session_id] = handler_task

    try:
        await handler_task
    except asyncio.CancelledError:
        pass
    finally:
        if _session_handler_tasks.get(session_id) is handler_task:
            del _session_handler_tasks[session_id]


async def _handle_voice_pipeline_v2(websocket: WebSocket, session_id: str) -> None:
    try:
        persona_id = await _get_default_persona_id()
        anonymous_user_id = str(uuid.uuid4())
        db_session_id = await create_session(persona_id=persona_id, user_id=anonymous_user_id, session_id=session_id)
        existing_session = await _load_session(db_session_id)
        voice_id = existing_session.get("selected_voice") if existing_session else None
        if not voice_id:
            try:
                voice_id = await get_persona_voice_id(persona_id)
            except Exception:
                voice_id = "en-IN-NeerjaNeural"
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

    conversation_mgr = ConversationManager()
    if existing_session:
        try:
            await conversation_mgr.load_from_db(db_session_id)
        except Exception:
            pass

    vad = VADBuffer(sample_rate=settings.audio_sample_rate)

    state = SessionPipelineState(
        session_id=session_id,
        db_session_id=db_session_id,
        persona_id=persona_id,
        voice_id=voice_id,
        websocket=websocket,
        audio_in_queue=asyncio.Queue(maxsize=settings.ws_queue_max_size),
        text_in_queue=asyncio.Queue(maxsize=settings.ws_queue_max_size),
        sentence_queue=asyncio.Queue(maxsize=settings.ws_queue_max_size),
        audio_out_queue=asyncio.Queue(maxsize=settings.ws_queue_max_size),
        control_queue=asyncio.Queue(maxsize=settings.ws_queue_max_size),
        ws_event_queue=asyncio.Queue(maxsize=settings.ws_queue_max_size),
        conversation_mgr=conversation_mgr,
        vad=vad,
        speech_detected=asyncio.Event(),
        cancelled_turns=set(),
    )

    pipeline = FiveQueuePipeline(
        audio_executor=websocket.app.state.audio_executor,
        embedding_executor=websocket.app.state.embedding_executor,
    )
    pipeline.start_pipeline(state)

    try:
        while True:
            event = await state.control_queue.get()
            if event is None:
                break
            if event.get("type") in ("disconnect", "stop_call"):
                break
            if event.get("type") == "start_call":
                if state.call_start_time is None:
                    state.call_start_time = time.perf_counter()
            elif event.get("type") == "voice_select":
                data = event["data"]
                state.voice_id = data.get("voice_id") or state.voice_id
                safe_put_nowait(state.ws_event_queue, make_event(state, "status", message=f"voice_selected:{state.voice_id}"))
            elif event.get("type") == "cancel_turn":
                await pipeline.handle_barge_in(state)
            elif event.get("type") == "force_stt":
                await pipeline.handle_barge_in(state)
                vad_instance = state.vad
                audio_data = await asyncio.get_running_loop().run_in_executor(
                    pipeline.audio_executor, vad_instance.flush
                )
                if not audio_data:
                    safe_put_nowait(state.ws_event_queue, make_event(state, "status", message="idle"))
                    continue
                wav_audio = await asyncio.get_running_loop().run_in_executor(
                    pipeline.audio_executor, pcm_to_wav, audio_data, settings.audio_sample_rate
                )
                stt_start = time.perf_counter()
                try:
                    user_text = await asyncio.wait_for(transcribe_audio(wav_audio), timeout=15)
                except asyncio.TimeoutError:
                    safe_put_nowait(state.ws_event_queue, make_event(state, "error", message="stt_timeout"))
                    safe_put_nowait(state.ws_event_queue, make_event(state, "status", message="idle"))
                    continue
                stt_latency_ms = int((time.perf_counter() - stt_start) * 1000)
                if not user_text or is_noisy_transcription(user_text):
                    safe_put_nowait(state.ws_event_queue, make_event(state, "error", message="empty_transcript"))
                    safe_put_nowait(state.ws_event_queue, make_event(state, "status", message="idle"))
                    continue
                state.user_pcm_buffer.clear()
                safe_put_nowait(
                    state.ws_event_queue,
                    make_event(state, "transcript_final", role="user", text=user_text, stt_latency_ms=stt_latency_ms),
                )
                safe_put_nowait(state.text_in_queue, TextInMessage(
                    session_id=state.session_id,
                    text=user_text,
                    stt_latency_ms=stt_latency_ms,
                ))
            elif event.get("type") == "external_transcript":
                data = event["data"]
                safe_put_nowait(state.text_in_queue, TextInMessage(
                    session_id=state.session_id,
                    text=data.get("text", ""),
                    stt_latency_ms=None,
                ))
    finally:
        await pipeline.stop_pipeline(state)
        recording_url = None
        try:
            user_pcm = bytes(state.user_pcm_buffer)
            ai_segments = manager.get_ai_segments(session_id)
            if user_pcm or ai_segments:
                composed = await asyncio.get_running_loop().run_in_executor(
                    pipeline.audio_executor,
                    compose_call_recording,
                    user_pcm,
                    ai_segments,
                    settings.audio_sample_rate,
                )
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
