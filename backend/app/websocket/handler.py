import json
import logging
import asyncio
from datetime import datetime, timezone
from collections import deque
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.websocket.manager import manager
from app.services.vad import VADBuffer
from app.services.audio import convert_to_wav, decode_to_pcm, pcm_to_wav
from app.services.stt import transcribe_audio
from app.services.llm import generate_response
from app.services.tts import synthesize_speech
from app.services.rag import retrieve_context
from app.services.session import save_turn, end_session, create_session
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


@router.websocket("/ws/voice/{session_id}")
async def websocket_voice(websocket: WebSocket, session_id: str, token: str = Query(...)):
    supabase = get_supabase()
    try:
        user = supabase.auth.get_user(token)
        if not user or not user.user:
            await websocket.close(code=4001, reason="Unauthorized")
            return
    except Exception:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await manager.connect(session_id, websocket)
    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS connected session={session_id}"})

    vad = VADBuffer(sample_rate=settings.audio_sample_rate)
    conversation: list[dict[str, str]] = []
    persona_id = "default"
    voice_id = "en-IN-NeerjaNeural"
    is_playing = False
    filler_sent = False
    db_session_id = None

    try:
        await manager.send_json(session_id, {"type": "status", "message": "connected"})
        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS status connected session={session_id}"})

        while True:
            message = await websocket.receive()
            await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "debug", "msg": f"WS receive session={session_id} message_keys={list(message.keys())}"})

            if "bytes" in message:
                chunk = message["bytes"]
                await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS audio chunk session={session_id} bytes={len(chunk)} playing={is_playing}"})
                await manager.send_json(session_id, {"type": "status", "message": "upload_received"})
                if is_playing:
                    is_playing = False
                    await manager.send_json(session_id, {"type": "status", "message": "interrupted"})
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS playback interrupted session={session_id}"})

                try:
                    chunk = decode_to_pcm(chunk, sample_rate=settings.audio_sample_rate)
                except Exception as exc:
                    await manager.send_json(session_id, {"type": "error", "message": f"decode_failed:{str(exc)}"})
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS decode failed session={session_id} error={exc}"})
                    continue

                await manager.send_json(session_id, {"type": "status", "message": "decoded"})
                vad_frame_ms = 30
                frame_size = int(settings.audio_sample_rate * 2 * (vad_frame_ms / 1000))
                await manager.send_json(session_id, {"type": "status", "message": "vading"})
                vad_frames = 0
                speech_ended = False
                audio_data = None
                for i in range(0, len(chunk), frame_size):
                    frame = bytes(chunk[i:i + frame_size])
                    if len(frame) == frame_size:
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

                if not speech_ended:
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS VAD no speech end detected session={session_id} vad_frames={vad_frames} chunk_len={len(chunk)}"})
                    if len(chunk) >= frame_size:
                        audio_data = chunk
                        speech_ended = True

                if speech_ended and audio_data:
                    await manager.send_json(session_id, {"type": "status", "message": "processing"})
                    await manager.send_json(session_id, {"type": "status", "message": "transcribing"})
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS speech ended session={session_id} audio_len={len(audio_data)}"})
                    wav_audio = pcm_to_wav(audio_data, sample_rate=settings.audio_sample_rate)
                    try:
                        user_text = await asyncio.wait_for(transcribe_audio(wav_audio), timeout=15)
                    except asyncio.TimeoutError:
                        await manager.send_json(session_id, {"type": "error", "message": "stt_timeout"})
                        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS STT timeout session={session_id}"})
                        continue
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS STT session={session_id} text={user_text}"})
                    await manager.send_json(session_id, {"type": "status", "message": "transcribed"})
                    if not user_text:
                        await manager.send_json(session_id, {"type": "error", "message": "empty_transcript"})
                        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS empty transcript session={session_id}"})
                        continue

                    conversation.append({"role": "user", "content": user_text})
                    target_session = db_session_id or session_id
                    await save_turn(target_session, "user", user_text)

                    await manager.send_json(session_id, {"type": "status", "message": "retrieving_context"})
                    try:
                        context = await asyncio.wait_for(retrieve_context(user_text), timeout=10)
                    except asyncio.TimeoutError:
                        context = []
                        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS RAG timeout session={session_id}"})
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS RAG context session={session_id} chunks={len(context) if context else 0}"})
                    await manager.send_json(session_id, {"type": "status", "message": "thinking"})
                    try:
                        response_text = await asyncio.wait_for(generate_response(conversation, "You are a helpful voice assistant."), timeout=30)
                    except asyncio.TimeoutError:
                        response_text = "I'm sorry, I'm taking too long to respond. Please try again."
                        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS LLM timeout session={session_id}"})
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS LLM response session={session_id} text={response_text}"})
                    conversation.append({"role": "assistant", "content": response_text})
                    await save_turn(target_session, "assistant", response_text)

                    await manager.send_json(session_id, {"type": "status", "message": "speaking"})
                    try:
                        audio_data = await asyncio.wait_for(synthesize_speech(response_text, voice_id), timeout=20)
                    except asyncio.TimeoutError:
                        await manager.send_json(session_id, {"type": "error", "message": "tts_timeout"})
                        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS TTS timeout session={session_id}"})
                        continue
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS TTS session={session_id} audio_len={len(audio_data)}"})
                    is_playing = True
                    await manager.send_bytes(session_id, audio_data)
                    await manager.send_json(session_id, {"type": "response_audio", "text": response_text})
                    is_playing = False
                    await manager.send_json(session_id, {"type": "status", "message": "response_ready"})
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS response sent session={session_id}"})

            elif "text" in message:
                data = json.loads(message["text"])
                msg_type = data.get("type")
                await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS text message session={session_id} type={msg_type}"})

                if msg_type == "auth":
                    persona_id = data.get("persona_id", persona_id)
                    voice_id = data.get("voice_id", voice_id)
                    user_id = data.get("user_id")
                    db_session_id = await create_session(persona_id, user_id=user_id)
                    await manager.send_json(session_id, {"type": "status", "message": "authenticated"})
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS authenticated session={session_id} persona={persona_id} voice={voice_id} db_session={db_session_id}"})

                elif msg_type == "voice_select":
                    voice_id = data.get("voice_id", voice_id)
                    await manager.send_json(session_id, {"type": "status", "message": f"voice_selected:{voice_id}"})
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS voice selected session={session_id} voice={voice_id}"})

                elif msg_type == "stop_playback":
                    is_playing = False
                    await manager.send_json(session_id, {"type": "status", "message": "playback_stopped"})
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS playback stopped session={session_id}"})

                elif msg_type == "transcript":
                    user_text = data.get("text", "")
                    if not user_text:
                        continue
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS transcript session={session_id} text={user_text}"})
                    conversation.append({"role": "user", "content": user_text})
                    target_session = db_session_id or session_id
                    await save_turn(target_session, "user", user_text)

                    context = await retrieve_context(user_text)
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS RAG context session={session_id} chunks={len(context) if context else 0}"})
                    system_prompt = "You are a helpful voice assistant."
                    response_text = await generate_response(conversation, system_prompt)
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS LLM response session={session_id} text={response_text}"})
                    conversation.append({"role": "assistant", "content": response_text})
                    await save_turn(target_session, "assistant", response_text)

                    try:
                        audio_data = await synthesize_speech(response_text, voice_id)
                        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS TTS session={session_id} audio_len={len(audio_data)}"})
                        is_playing = True
                        await manager.send_bytes(session_id, audio_data)
                        await manager.send_json(session_id, {"type": "response_audio", "text": response_text})
                        is_playing = False
                        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS response sent session={session_id}"})
                    except Exception as exc:
                        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS TTS failed session={session_id} error={exc}"})
                        await manager.send_json(session_id, {
                            "type": "error",
                            "message": f"tts_failed:{str(exc)}",
                        })

    except WebSocketDisconnect:
        target_session = db_session_id or session_id
        await end_session(target_session)
        manager.disconnect(session_id)
        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS disconnected session={session_id} target_session={target_session}"})
