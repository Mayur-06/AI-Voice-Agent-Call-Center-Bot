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
    mock_ws.receive = AsyncMock(side_effect=WebSocketDisconnect())
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
        await ws_router.routes[0].endpoint(mock_ws, "session-1")
        mock_manager.connect.assert_called_once_with("session-1", mock_ws)
        mock_manager.disconnect.assert_called_once_with("session-1")
        mock_create_session.assert_called_once_with(
            persona_id="default",
            user_id=ANY,
            session_id="session-1",
        )


@pytest.mark.asyncio
async def test_websocket_voice_auth_message():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.receive = AsyncMock(side_effect=[
        {"text": '{"type": "auth", "persona_id": "p1", "voice_id": "v1"}'},
        WebSocketDisconnect(),
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
        await ws_router.routes[0].endpoint(mock_ws, "session-1")
        mock_manager.send_json.assert_called()
        mock_create_session.assert_called_once_with(
            persona_id="default",
            user_id=ANY,
            session_id="session-1",
        )


@pytest.mark.asyncio
async def test_websocket_voice_stop_playback():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.receive = AsyncMock(side_effect=[
        {"text": '{"type": "stop_playback"}'},
        WebSocketDisconnect(),
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
        await ws_router.routes[0].endpoint(mock_ws, "session-1")
        mock_manager.send_json.assert_called()
        mock_create_session.assert_called_once_with(
            persona_id="default",
            user_id=ANY,
            session_id="session-1",
        )


@pytest.mark.asyncio
async def test_websocket_voice_select():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.receive = AsyncMock(side_effect=[
        {"text": '{"type": "voice_select", "voice_id": "en-US-GuyNeural"}'},
        WebSocketDisconnect(),
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
        await ws_router.routes[0].endpoint(mock_ws, "session-1")
        calls = [call.args[1] for call in mock_manager.send_json.call_args_list]
        assert any("voice_selected" in str(c) for c in calls)
        mock_create_session.assert_called_once_with(
            persona_id="default",
            user_id=ANY,
            session_id="session-1",
        )


@pytest.mark.asyncio
async def test_websocket_transcript_message():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.receive = AsyncMock(side_effect=[
        {"text": '{"type": "transcript", "text": "Hello"}'},
        WebSocketDisconnect(),
    ])
    with patch("app.websocket.handler.manager") as mock_manager, \
         patch("app.services.voice_pipeline.manager", mock_manager), \
         patch("app.services.tts.manager", mock_manager), \
         patch("app.websocket.handler.create_session", new_callable=AsyncMock) as mock_create_session, \
         patch("app.websocket.handler.end_session", new_callable=AsyncMock), \
         patch("app.services.voice_pipeline.analyze_sentiment", new_callable=AsyncMock) as mock_analyze_sentiment, \
          patch("app.services.voice_pipeline.save_turn", new_callable=AsyncMock), \
          patch("app.services.voice_pipeline.retrieve_relevant_chunks", new_callable=AsyncMock) as mock_retrieve, \
         patch("app.services.voice_pipeline.generate_response_stream") as mock_generate_stream, \
         patch("app.services.tts.synthesize_speech_stream") as mock_tts_stream, \
         patch("app.websocket.handler.get_persona_voice_id", new_callable=AsyncMock) as mock_get_voice, \
         patch("app.websocket.handler._get_default_persona_id", new_callable=AsyncMock) as mock_get_default_persona, \
         patch("app.websocket.handler._load_session", new_callable=AsyncMock) as mock_load_session:
        mock_get_voice.return_value = "en-IN-NeerjaNeural"
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
        await ws_router.routes[0].endpoint(mock_ws, "session-1")
        mock_manager.send_json.assert_called()
        mock_manager.send_bytes.assert_called()
        mock_create_session.assert_called_once_with(
            persona_id="default",
            user_id=ANY,
            session_id="session-1",
        )
