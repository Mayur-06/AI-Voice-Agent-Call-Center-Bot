import logging
import asyncio
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketState
from app.websocket.manager import manager, _append_log
from app.services.vad import VADBuffer
from app.services.audio_processor import compose_call_recording, save_session_recording
from app.services.conversation_mgr import ConversationManager
from app.services.call_summarizer import generate_call_summary
from app.services.session import create_session, end_session, _get_default_persona_id
from app.services.tts import get_persona_voice_id
from app.services.llm import get_persona_system_prompt
from app.models.database import get_supabase, run_supabase
from app.config import settings
from app.orchestration.pipeline import SessionPipelineState, FiveQueuePipeline, safe_put_nowait, make_event, TextInMessage

logger = logging.getLogger(__name__)
router = APIRouter()

# The live socket is tracked alongside its handler so a reconnect can tell a
# genuine second client apart from a handler that is merely finishing teardown.
_session_handler_tasks: dict[str, tuple[asyncio.Task, WebSocket]] = {}
_session_handler_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

# Ending a call writes the recording and generates a summary, which takes
# several seconds. A client reconnecting after a dropped socket must wait for
# that to finish rather than be turned away - its own retry backoff (1s, 2s,
# 4s) falls entirely inside that window, so rejecting it killed the call.
_TEARDOWN_WAIT_SECONDS = 45


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
        existing = _session_handler_tasks.get(session_id)
        if existing is not None and existing[0].done():
            del _session_handler_tasks[session_id]
            existing = None

        if existing is not None:
            existing_task, existing_ws = existing
            if existing_ws.client_state == WebSocketState.CONNECTED:
                # A second client really is on this session; turn it away.
                try:
                    await websocket.accept()
                    await websocket.send_json({"type": "info", "message": "session_already_active"})
                    await websocket.close()
                except Exception:
                    pass
                return

            # The old socket is gone, so this is a reconnect and the previous
            # handler is only completing its teardown. Let it finish, then
            # carry on with the new socket.
            await _log_stage(session_id, "AWAITING_PREVIOUS_TEARDOWN")
            try:
                await asyncio.wait_for(asyncio.shield(existing_task), timeout=_TEARDOWN_WAIT_SECONDS)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                logger.warning("TEARDOWN_WAIT_EXPIRED session=%s", session_id)
            except Exception:
                logger.exception("TEARDOWN_FAILED session=%s", session_id)
            _session_handler_tasks.pop(session_id, None)

        await manager.connect(session_id, websocket)
        await _log_stage(session_id, "CONNECTION_ESTABLISHED")

        handler_task = asyncio.create_task(_handle_voice_pipeline_v2(websocket, session_id))
        _session_handler_tasks[session_id] = (handler_task, websocket)

    try:
        await handler_task
    except asyncio.CancelledError:
        pass
    finally:
        tracked = _session_handler_tasks.get(session_id)
        if tracked is not None and tracked[0] is handler_task:
            del _session_handler_tasks[session_id]
        lock = _session_handler_locks.get(session_id)
        if lock is not None and not lock.locked():
            _session_handler_locks.pop(session_id, None)


async def _handle_voice_pipeline_v2(websocket: WebSocket, session_id: str) -> None:
    try:
        # The persona must come from the session the caller actually created:
        # deriving it from _get_default_persona_id() gave every call the first
        # persona in the table, so the selected persona's system prompt was
        # never used and RAG filtered on the wrong persona_id.
        existing_session = await _load_session(session_id)
        if existing_session:
            # A completed session is immutable. The client route has a guard
            # too, but this check prevents a stale URL or custom client from
            # reopening the call through the WebSocket directly.
            if existing_session.get("status") == "ended" or existing_session.get("ended_at"):
                await websocket.send_json({"type": "error", "message": "session_ended"})
                await websocket.close(code=1008, reason="Session has ended")
                return
            db_session_id = str(existing_session["id"])
            persona_id = str(existing_session.get("persona_id") or "") or await _get_default_persona_id()
        else:
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

    try:
        system_prompt = await get_persona_system_prompt(persona_id)
    except Exception:
        system_prompt = "You are a helpful voice assistant."

    conversation_mgr = ConversationManager()
    # Reconnects resume an existing session, so turn numbering has to continue
    # from what is already stored. Restarting at 0 gave the new turns sequence
    # numbers that collided with the old ones, and every ordered read of the
    # transcript came back interleaved.
    resume_sequence = 0
    if existing_session:
        try:
            await conversation_mgr.load_from_db(db_session_id)
            resume_sequence = len(conversation_mgr)
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
        system_prompt=system_prompt,
        vad=vad,
        speech_detected=asyncio.Event(),
        cancelled_turns=set(),
        next_sequence_number=resume_sequence,
    )

    pipeline = FiveQueuePipeline(
        audio_executor=websocket.app.state.audio_executor,
        vad_executor=websocket.app.state.vad_executor,
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
                logger.info("HANDLER_START_CALL session=%s call_started=%s call_start_time=%s", state.session_id, state.call_started, state.call_start_time)
            elif event.get("type") == "voice_select":
                data = event["data"]
                state.voice_id = data.get("voice_id") or state.voice_id
                safe_put_nowait(state.ws_event_queue, make_event(state, "status", message=f"voice_selected:{state.voice_id}"))
            elif event.get("type") == "playback_state":
                playing = bool((event.get("data") or {}).get("playing"))
                if playing:
                    state.playback_finished.clear()
                    if state.vad is not None:
                        state.vad.muted = True
                else:
                    state.playback_finished.set()
                logger.info("PLAYBACK_STATE session=%s playing=%s", state.session_id, playing)
            elif event.get("type") == "cancel_turn":
                await pipeline.handle_barge_in(state)
            elif event.get("type") == "force_stt":
                logger.info("FORCE_STT_RECEIVED session=%s", state.session_id)
                await pipeline.handle_barge_in(state)
                # Must run on the same single-threaded executor as
                # process_bytes: flushing from the audio pool raced the VAD
                # loop and could corrupt the buffer mid-utterance.
                audio_data = await asyncio.get_running_loop().run_in_executor(
                    pipeline.vad_executor, state.vad.flush
                )
                if not audio_data:
                    safe_put_nowait(state.ws_event_queue, make_event(state, "status", message="idle"))
                    continue
                # Dispatched through the normal STT path so the control loop
                # stays responsive to stop_call and barge-in while it runs.
                from app.orchestration.stages import _transcribe
                stt_task = asyncio.create_task(_transcribe(audio_data, pipeline.audio_executor))
                state.user_pcm_buffer.clear()
                # voiced_ms None: an explicit "stop listening" is a deliberate
                # request to transcribe, so short stock phrases are trusted.
                safe_put_nowait(state.stt_pending_queue, (stt_task, None, None, None))
            elif event.get("type") == "external_transcript":
                data = event["data"] or {}
                nested = data.get("data") if isinstance(data.get("data"), dict) else {}
                text = (nested.get("text") or data.get("text") or "").strip()
                if not text:
                    safe_put_nowait(
                        state.ws_event_queue,
                        make_event(state, "error", message="empty_transcript"),
                    )
                    continue
                safe_put_nowait(state.ws_event_queue, make_event(
                    state, "transcript_final", role="user", text=text,
                ))
                safe_put_nowait(state.text_in_queue, TextInMessage(
                    session_id=state.session_id,
                    text=text,
                    stt_latency_ms=None,
                ))
    finally:
        await pipeline.stop_pipeline(state)

        async def _build_recording() -> str | None:
            try:
                user_pcm = bytes(state.user_pcm_buffer)
                ai_segments = manager.get_ai_segments(session_id)
                if not (user_pcm or ai_segments):
                    return None
                composed = await asyncio.get_running_loop().run_in_executor(
                    pipeline.audio_executor,
                    compose_call_recording,
                    user_pcm,
                    ai_segments,
                    settings.audio_sample_rate,
                )
                if composed:
                    return await save_session_recording(db_session_id, composed)
            except Exception:
                logger.exception("SAVE_RECORDING_FAILED session=%s", session_id)
            return None

        async def _build_summary() -> str:
            if len(conversation_mgr) == 0:
                return ""
            try:
                return await asyncio.wait_for(
                    generate_call_summary(conversation_mgr.get_history()), timeout=30
                )
            except asyncio.TimeoutError:
                logger.warning("SUMMARY_TIMEOUT session=%s", session_id)
            except Exception:
                logger.exception("SUMMARY_FAILED session=%s", session_id)
            return ""

        # Independent work, so it runs concurrently. Run one after the other,
        # every teardown cost the sum of both - and a client reconnecting after
        # a dropped socket waits out that whole window before it can rejoin.
        recording_url, summary = await asyncio.gather(
            _build_recording(), _build_summary()
        )

        await end_session(db_session_id, recording_url=recording_url, summary=summary or None)
        current_ws = manager.active_connections.get(session_id)
        if current_ws is None or current_ws is websocket:
            manager.disconnect(session_id)
        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS disconnected session={session_id} target_session={db_session_id}"})
        from app.services.call_session_logger import close_session
        await close_session(session_id)
