import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json as json_module
import logging
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import WebSocket, WebSocketDisconnect
from httpx import Response
from app.websocket.handler import router as ws_router


logger = logging.getLogger("test_pipeline")


def _mock_response(status_code=200, json_data=None):
    content = json_module.dumps(json_data or {}).encode()
    response = Response(status_code, content=content)
    response.raise_for_status = MagicMock()
    return response


def _make_pcm_chunk(duration_ms: int = 250) -> bytes:
    samples = int(16000 * 2 * (duration_ms / 1000))
    return b"\x00\x00" * (samples // 2)


def _vad_side_effect(audio_chunk: bytes):
    frame_count = 0
    max_frames = int(len(audio_chunk) / int(16000 * 2 * (30 / 1000)))

    def side_effect(frame):
        nonlocal frame_count
        frame_count += 1
        if frame_count >= max_frames:
            return audio_chunk, True
        return None, False

    return side_effect


def _get_session_logs(session_id: str):
    from app.websocket.handler import session_logs
    return list(session_logs.get(session_id, []))


@pytest.mark.asyncio
async def test_pipeline_audio_to_llm_to_speech():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.query_params = {"token": "valid-token"}

    audio_chunk = _make_pcm_chunk(250)

    with patch("app.websocket.handler.manager") as mock_manager, \
         patch("app.websocket.handler.create_session", new_callable=AsyncMock) as mock_create_session, \
         patch("app.websocket.handler.end_session", new_callable=AsyncMock) as mock_end_session, \
         patch("app.websocket.handler.get_supabase") as mock_get_supabase, \
         patch("app.websocket.handler.VADBuffer") as mock_vad_cls, \
         patch("app.websocket.handler.pcm_to_wav") as mock_convert, \
         patch("app.websocket.handler.decode_to_pcm") as mock_decode, \
         patch("app.websocket.handler.transcribe_audio") as mock_stt, \
         patch("app.websocket.handler.retrieve_context") as mock_rag, \
         patch("app.websocket.handler.generate_response") as mock_llm, \
         patch("app.websocket.handler.synthesize_speech") as mock_tts, \
         patch("app.websocket.handler.save_turn", new_callable=AsyncMock):
        mock_supabase = MagicMock()
        mock_supabase.auth.get_user.return_value.user = MagicMock()
        mock_get_supabase.return_value = mock_supabase

        mock_vad = MagicMock()
        mock_vad.process = MagicMock(side_effect=_vad_side_effect(audio_chunk))
        mock_vad_cls.return_value = mock_vad

        mock_decode.return_value = audio_chunk
        mock_convert.return_value = b"wav-audio"
        mock_stt.return_value = "What is in the document?"
        mock_rag.return_value = [{"text": "Context from document: policy is 20 days."}]
        mock_llm.return_value = "According to the document, the policy is 20 days."
        mock_tts.return_value = b"tts-audio-bytes"

        mock_create_session.return_value = "db-session-1"
        mock_manager.connect = AsyncMock()
        mock_manager.disconnect = MagicMock()
        mock_manager.send_json = AsyncMock()
        mock_manager.send_bytes = AsyncMock()

        mock_ws.receive = AsyncMock(side_effect=[
            {"bytes": audio_chunk},
            WebSocketDisconnect(),
        ])

        await ws_router.routes[0].endpoint(mock_ws, "session-1")

    logs = _get_session_logs("session-1")
    messages = [entry["msg"] for entry in logs]
    assert any("WS connected" in m for m in messages)
    assert any("WS status connected" in m for m in messages)
    assert any("WS audio chunk" in m for m in messages)
    assert any("WS speech ended" in m for m in messages)
    assert any("WS STT" in m and "What is in the document?" in m for m in messages)
    assert any("WS RAG context" in m for m in messages)
    assert any("WS LLM response" in m and "According to the document" in m for m in messages)
    assert any("WS TTS" in m for m in messages)
    assert any("WS response sent" in m for m in messages)
    assert any("WS disconnected" in m for m in messages)

    mock_convert.assert_called_once()
    mock_stt.assert_called_once()
    mock_rag.assert_called_once()
    mock_llm.assert_called_once()
    mock_tts.assert_called_once()
    mock_manager.send_bytes.assert_called_once_with("session-1", b"tts-audio-bytes")
    mock_manager.send_json.assert_any_call("session-1", {
        "type": "response_audio",
        "text": "According to the document, the policy is 20 days.",
    })


@pytest.mark.asyncio
async def test_pipeline_text_transcript_flow():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.query_params = {"token": "valid-token"}

    with patch("app.websocket.handler.manager") as mock_manager, \
         patch("app.websocket.handler.create_session", new_callable=AsyncMock) as mock_create_session, \
         patch("app.websocket.handler.end_session", new_callable=AsyncMock) as mock_end_session, \
         patch("app.websocket.handler.get_supabase") as mock_get_supabase, \
         patch("app.websocket.handler.retrieve_context") as mock_rag, \
         patch("app.websocket.handler.generate_response") as mock_llm, \
         patch("app.websocket.handler.synthesize_speech") as mock_tts, \
         patch("app.websocket.handler.save_turn", new_callable=AsyncMock):
        mock_supabase = MagicMock()
        mock_supabase.auth.get_user.return_value.user = MagicMock()
        mock_get_supabase.return_value = mock_supabase

        mock_rag.return_value = [{"text": "Document says refunds take 5-7 days."}]
        mock_llm.return_value = "Refunds take 5-7 business days."
        mock_tts.return_value = b"tts-audio"

        mock_create_session.return_value = "db-session-1"
        mock_manager.connect = AsyncMock()
        mock_manager.disconnect = MagicMock()
        mock_manager.send_json = AsyncMock()
        mock_manager.send_bytes = AsyncMock()

        mock_ws.receive = AsyncMock(side_effect=[
            {"text": '{"type": "transcript", "text": "When is my refund?"}'},
            WebSocketDisconnect(),
        ])

        await ws_router.routes[0].endpoint(mock_ws, "session-1")

    logs = _get_session_logs("session-1")
    messages = [entry["msg"] for entry in logs]
    assert any("WS text message session=session-1 type=transcript" in m for m in messages)
    assert any("WS transcript session=session-1 text=When is my refund?" in m for m in messages)
    assert any("WS RAG context session=session-1 chunks=1" in m for m in messages)
    assert any("WS LLM response session=session-1 text=Refunds take 5-7 business days." in m for m in messages)
    assert any("WS TTS session=session-1 audio_len=9" in m for m in messages)
    assert any("WS response sent session=session-1" in m for m in messages)

    mock_manager.send_bytes.assert_called_once_with("session-1", b"tts-audio")
    mock_manager.send_json.assert_any_call("session-1", {
        "type": "response_audio",
        "text": "Refunds take 5-7 business days.",
    })


@pytest.mark.asyncio
async def test_pipeline_empty_transcript():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.query_params = {"token": "valid-token"}

    with patch("app.websocket.handler.manager") as mock_manager, \
         patch("app.websocket.handler.create_session", new_callable=AsyncMock) as mock_create_session, \
         patch("app.websocket.handler.end_session", new_callable=AsyncMock), \
         patch("app.websocket.handler.get_supabase") as mock_get_supabase, \
         patch("app.websocket.handler.VADBuffer") as mock_vad_cls, \
         patch("app.websocket.handler.pcm_to_wav") as mock_convert, \
         patch("app.websocket.handler.decode_to_pcm") as mock_decode, \
         patch("app.websocket.handler.transcribe_audio") as mock_stt, \
         patch("app.websocket.handler.save_turn", new_callable=AsyncMock):
        mock_supabase = MagicMock()
        mock_supabase.auth.get_user.return_value.user = MagicMock()
        mock_get_supabase.return_value = mock_supabase

        mock_vad = MagicMock()
        mock_vad.process = MagicMock(return_value=(b"audio", True))
        mock_vad_cls.return_value = mock_vad

        mock_decode.return_value = _make_pcm_chunk(250)
        mock_convert.return_value = b"wav-audio"
        mock_stt.return_value = ""

        mock_create_session.return_value = "db-session-1"
        mock_manager.connect = AsyncMock()
        mock_manager.disconnect = MagicMock()
        mock_manager.send_json = AsyncMock()
        mock_manager.send_bytes = AsyncMock()

        mock_ws.receive = AsyncMock(side_effect=[
            {"bytes": _make_pcm_chunk(250)},
            WebSocketDisconnect(),
        ])

        await ws_router.routes[0].endpoint(mock_ws, "session-1")

    logs = _get_session_logs("session-1")
    messages = [entry["msg"] for entry in logs]
    assert any("WS empty transcript" in m for m in messages)
    mock_manager.send_json.assert_any_call("session-1", {"type": "error", "message": "empty_transcript"})


@pytest.mark.asyncio
async def test_pipeline_auth_flow():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.query_params = {"token": "valid-token"}

    with patch("app.websocket.handler.manager") as mock_manager, \
         patch("app.websocket.handler.create_session", new_callable=AsyncMock) as mock_create_session, \
         patch("app.websocket.handler.end_session", new_callable=AsyncMock) as mock_end_session, \
         patch("app.websocket.handler.get_supabase") as mock_get_supabase:
        mock_supabase = MagicMock()
        mock_supabase.auth.get_user.return_value.user = MagicMock()
        mock_get_supabase.return_value = mock_supabase

        mock_create_session.return_value = "db-session-1"
        mock_manager.connect = AsyncMock()
        mock_manager.disconnect = MagicMock()
        mock_manager.send_json = AsyncMock()
        mock_manager.send_bytes = AsyncMock()

        mock_ws.receive = AsyncMock(side_effect=[
            {"text": '{"type": "auth", "persona_id": "p1", "voice_id": "v1", "user_id": "u1"}'},
            WebSocketDisconnect(),
        ])

        await ws_router.routes[0].endpoint(mock_ws, "session-1")

    logs = _get_session_logs("session-1")
    messages = [entry["msg"] for entry in logs]
    assert any("WS authenticated" in m for m in messages)
    assert any("WS disconnected" in m for m in messages)
    mock_create_session.assert_called_once_with("p1", user_id="u1")
