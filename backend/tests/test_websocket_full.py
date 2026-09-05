import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json as json_module
import logging
import pytest
from unittest.mock import MagicMock, patch, AsyncMock, ANY
from fastapi import WebSocket, WebSocketDisconnect
from httpx import Response
from app.websocket.handler import router as ws_router


logger = logging.getLogger("test_websocket_full")


def _mock_response(status_code=200, json_data=None):
    content = json_module.dumps(json_data or {}).encode()
    response = Response(status_code, content=content)
    response.raise_for_status = MagicMock()
    return response


def _get_session_logs(session_id: str):
    from app.websocket.manager import session_logs
    return list(session_logs.get(session_id, []))


@pytest.mark.asyncio
async def test_websocket_connect_and_disconnect():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.receive = AsyncMock(side_effect=[
        {"type": "websocket.disconnect"},
    ])
    with patch("app.websocket.handler.manager") as mock_manager, \
         patch("app.websocket.handler.create_session", new_callable=AsyncMock) as mock_create_session, \
         patch("app.websocket.handler.end_session", new_callable=AsyncMock) as mock_end_session, \
         patch("app.websocket.handler.get_persona_voice_id", new_callable=AsyncMock) as mock_get_voice, \
         patch("app.websocket.handler._get_default_persona_id", new_callable=AsyncMock) as mock_get_default_persona, \
         patch("app.websocket.handler._load_session", new_callable=AsyncMock) as mock_load_session:
        mock_get_voice.return_value = "en-IN-NeerjaNeural"
        mock_get_default_persona.return_value = "default"
        mock_load_session.return_value = None
        mock_create_session.return_value = "session-1"
        mock_manager.connect = AsyncMock()
        mock_manager.disconnect = MagicMock()
        mock_manager.send_json = AsyncMock()
        mock_manager.active_connections = {}
        await ws_router.routes[0].endpoint(mock_ws, "session-1")
        mock_manager.connect.assert_called_once_with("session-1", mock_ws)
        mock_manager.disconnect.assert_called_once_with("session-1")
        mock_create_session.assert_called_once_with(
            persona_id="default",
            user_id=ANY,
            session_id="session-1",
        )


@pytest.mark.asyncio
async def test_websocket_voice_stop_playback():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.receive = AsyncMock(side_effect=[
        {"type": "websocket.receive", "text": '{"type": "stop_playback"}'},
        {"type": "websocket.disconnect"},
    ])
    with patch("app.websocket.handler.manager") as mock_manager, \
         patch("app.websocket.handler.create_session", new_callable=AsyncMock) as mock_create_session, \
         patch("app.websocket.handler.end_session", new_callable=AsyncMock) as mock_end_session, \
         patch("app.websocket.handler.get_persona_voice_id", new_callable=AsyncMock) as mock_get_voice, \
         patch("app.websocket.handler._get_default_persona_id", new_callable=AsyncMock) as mock_get_default_persona, \
         patch("app.websocket.handler._load_session", new_callable=AsyncMock) as mock_load_session:
        mock_get_voice.return_value = "en-IN-NeerjaNeural"
        mock_get_default_persona.return_value = "default"
        mock_load_session.return_value = None
        mock_create_session.return_value = "session-1"
        mock_manager.connect = AsyncMock()
        mock_manager.disconnect = MagicMock()
        mock_manager.send_json = AsyncMock()
        mock_manager.active_connections = {}
        await ws_router.routes[0].endpoint(mock_ws, "session-1")
        mock_create_session.assert_called_once_with(
            persona_id="default",
            user_id=ANY,
            session_id="session-1",
        )


@pytest.mark.asyncio
async def test_websocket_voice_select():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.receive = AsyncMock(side_effect=[
        {"type": "websocket.receive", "text": '{"type": "voice_select", "voice_id": "en-US-GuyNeural"}'},
        {"type": "websocket.disconnect"},
    ])
    with patch("app.websocket.handler.manager") as mock_manager, \
         patch("app.websocket.handler.create_session", new_callable=AsyncMock) as mock_create_session, \
         patch("app.websocket.handler.end_session", new_callable=AsyncMock) as mock_end_session, \
         patch("app.websocket.handler.get_persona_voice_id", new_callable=AsyncMock) as mock_get_voice, \
         patch("app.websocket.handler._get_default_persona_id", new_callable=AsyncMock) as mock_get_default_persona, \
         patch("app.websocket.handler._load_session", new_callable=AsyncMock) as mock_load_session:
        mock_get_voice.return_value = "en-IN-NeerjaNeural"
        mock_get_default_persona.return_value = "default"
        mock_load_session.return_value = None
        mock_create_session.return_value = "session-1"
        mock_manager.connect = AsyncMock()
        mock_manager.disconnect = MagicMock()
        mock_manager.send_json = AsyncMock()
        mock_manager.active_connections = {}
        await ws_router.routes[0].endpoint(mock_ws, "session-1")
        mock_create_session.assert_called_once_with(
            persona_id="default",
            user_id=ANY,
            session_id="session-1",
        )


@pytest.mark.asyncio
async def test_websocket_transcript_message():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.receive = AsyncMock(side_effect=[
        {"type": "websocket.receive", "text": '{"type": "transcript", "text": "Hello"}'},
        {"type": "websocket.disconnect"},
    ])
    with patch("app.websocket.handler.manager") as mock_manager, \
         patch("app.websocket.handler.create_session", new_callable=AsyncMock) as mock_create_session, \
         patch("app.websocket.handler.end_session", new_callable=AsyncMock), \
         patch("app.orchestration.stages.analyze_sentiment", new_callable=AsyncMock) as mock_analyze_sentiment, \
         patch("app.orchestration.stages.save_turn", new_callable=AsyncMock), \
         patch("app.orchestration.stages.retrieve_relevant_chunks", new_callable=AsyncMock) as mock_retrieve, \
         patch("app.orchestration.stages.generate_response_stream") as mock_generate_stream, \
         patch("app.orchestration.stages.synthesize_speech_stream") as mock_tts_stream, \
         patch("app.orchestration.stages.get_persona_system_prompt", new_callable=AsyncMock) as mock_get_prompt, \
         patch("app.websocket.handler.get_persona_voice_id", new_callable=AsyncMock) as mock_get_voice, \
         patch("app.websocket.handler._get_default_persona_id", new_callable=AsyncMock) as mock_get_default_persona, \
         patch("app.websocket.handler._load_session", new_callable=AsyncMock) as mock_load_session:
        mock_get_voice.return_value = "en-IN-NeerjaNeural"
        mock_get_prompt.return_value = "You are a helpful assistant."
        mock_get_default_persona.return_value = "default"
        mock_load_session.return_value = None
        mock_retrieve.return_value = []
        mock_analyze_sentiment.return_value = "neutral"
        mock_create_session.return_value = "session-1"

        async def mock_generate_stream_fn(*args, **kwargs):
            yield "Hi!"

        mock_generate_stream.return_value = mock_generate_stream_fn()

        async def mock_tts_stream_fn(*args, **kwargs):
            yield b"audio"

        mock_tts_stream.return_value = mock_tts_stream_fn()
        mock_manager.connect = AsyncMock()
        mock_manager.disconnect = MagicMock()
        mock_manager.send_json = AsyncMock()
        mock_manager.send_bytes = AsyncMock()
        mock_manager.active_connections = {}
        await ws_router.routes[0].endpoint(mock_ws, "session-1")
        mock_create_session.assert_called_once_with(
            persona_id="default",
            user_id=ANY,
            session_id="session-1",
        )
