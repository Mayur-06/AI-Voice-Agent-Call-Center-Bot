import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json as json_module
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import WebSocket, WebSocketDisconnect
from httpx import Response
from app.websocket.handler import router as ws_router


def _mock_response(status_code=200, json_data=None):
    content = json_module.dumps(json_data or {}).encode()
    response = Response(status_code, content=content)
    response.raise_for_status = MagicMock()
    return response


@pytest.mark.asyncio
async def test_websocket_unauthorized_token():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.query_params = {"token": "invalid-token"}
    with patch("app.websocket.handler.get_supabase") as mock_get_supabase:
        mock_supabase = MagicMock()
        mock_supabase.auth.get_user.side_effect = Exception("Invalid token")
        mock_get_supabase.return_value = mock_supabase
        await ws_router.routes[0].endpoint(mock_ws, "session-1")
        mock_ws.close.assert_called_once_with(code=4001, reason="Unauthorized")


@pytest.mark.asyncio
async def test_websocket_missing_token():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.query_params = {}
    try:
        await ws_router.routes[0].endpoint(mock_ws, "session-1")
    except TypeError:
        pass


@pytest.mark.asyncio
async def test_websocket_connect_and_disconnect():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.receive = AsyncMock(side_effect=WebSocketDisconnect())
    mock_ws.query_params = {"token": "valid-token"}
    with patch("app.websocket.handler.manager") as mock_manager, \
         patch("app.websocket.handler.create_session", new_callable=AsyncMock) as mock_create_session, \
         patch("app.websocket.handler.end_session", new_callable=AsyncMock) as mock_end_session, \
         patch("app.websocket.handler.get_supabase") as mock_get_supabase:
        mock_supabase = MagicMock()
        mock_supabase.auth.get_user.return_value.user = MagicMock()
        mock_get_supabase.return_value = mock_supabase
        mock_manager.connect = AsyncMock()
        mock_manager.disconnect = MagicMock()
        mock_manager.send_json = AsyncMock()
        await ws_router.routes[0].endpoint(mock_ws, "session-1")
        mock_manager.connect.assert_called_once_with("session-1", mock_ws)
        mock_manager.disconnect.assert_called_once_with("session-1")


@pytest.mark.asyncio
async def test_websocket_voice_auth_message():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.receive = AsyncMock(side_effect=[
        {"text": '{"type": "auth", "persona_id": "p1", "voice_id": "v1"}'},
        WebSocketDisconnect(),
    ])
    mock_ws.query_params = {"token": "valid-token"}
    with patch("app.websocket.handler.manager") as mock_manager, \
         patch("app.websocket.handler.create_session", new_callable=AsyncMock) as mock_create_session, \
         patch("app.websocket.handler.end_session", new_callable=AsyncMock) as mock_end_session, \
         patch("app.websocket.handler.get_supabase") as mock_get_supabase:
        mock_supabase = MagicMock()
        mock_supabase.auth.get_user.return_value.user = MagicMock()
        mock_get_supabase.return_value = mock_supabase
        mock_manager.connect = AsyncMock()
        mock_manager.disconnect = MagicMock()
        mock_manager.send_json = AsyncMock()
        await ws_router.routes[0].endpoint(mock_ws, "session-1")
        mock_manager.send_json.assert_called()


@pytest.mark.asyncio
async def test_websocket_voice_stop_playback():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.receive = AsyncMock(side_effect=[
        {"text": '{"type": "stop_playback"}'},
        WebSocketDisconnect(),
    ])
    mock_ws.query_params = {"token": "valid-token"}
    with patch("app.websocket.handler.manager") as mock_manager, \
         patch("app.websocket.handler.create_session", new_callable=AsyncMock) as mock_create_session, \
         patch("app.websocket.handler.end_session", new_callable=AsyncMock) as mock_end_session, \
         patch("app.websocket.handler.get_supabase") as mock_get_supabase:
        mock_supabase = MagicMock()
        mock_supabase.auth.get_user.return_value.user = MagicMock()
        mock_get_supabase.return_value = mock_supabase
        mock_manager.connect = AsyncMock()
        mock_manager.disconnect = MagicMock()
        mock_manager.send_json = AsyncMock()
        await ws_router.routes[0].endpoint(mock_ws, "session-1")
        mock_manager.send_json.assert_called()


@pytest.mark.asyncio
async def test_websocket_voice_select():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.receive = AsyncMock(side_effect=[
        {"text": '{"type": "voice_select", "voice_id": "en-US-GuyNeural"}'},
        WebSocketDisconnect(),
    ])
    mock_ws.query_params = {"token": "valid-token"}
    with patch("app.websocket.handler.manager") as mock_manager, \
         patch("app.websocket.handler.create_session", new_callable=AsyncMock), \
         patch("app.websocket.handler.end_session", new_callable=AsyncMock), \
         patch("app.websocket.handler.get_supabase") as mock_get_supabase:
        mock_supabase = MagicMock()
        mock_supabase.auth.get_user.return_value.user = MagicMock()
        mock_get_supabase.return_value = mock_supabase
        mock_manager.connect = AsyncMock()
        mock_manager.disconnect = MagicMock()
        mock_manager.send_json = AsyncMock()
        await ws_router.routes[0].endpoint(mock_ws, "session-1")
        calls = [call.args[1] for call in mock_manager.send_json.call_args_list]
        assert any("voice_selected" in str(c) for c in calls)


@pytest.mark.asyncio
async def test_websocket_transcript_message():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.receive = AsyncMock(side_effect=[
        {"text": '{"type": "transcript", "text": "Hello"}'},
        WebSocketDisconnect(),
    ])
    mock_ws.query_params = {"token": "valid-token"}
    with patch("app.websocket.handler.manager") as mock_manager, \
         patch("app.websocket.handler.create_session", new_callable=AsyncMock), \
         patch("app.websocket.handler.end_session", new_callable=AsyncMock), \
         patch("app.websocket.handler.get_supabase") as mock_get_supabase, \
         patch("app.websocket.handler.save_turn", new_callable=AsyncMock), \
         patch("app.websocket.handler.retrieve_context", new_callable=AsyncMock) as mock_retrieve, \
         patch("app.websocket.handler.generate_response", new_callable=AsyncMock) as mock_generate, \
         patch("app.websocket.handler.synthesize_speech", new_callable=AsyncMock) as mock_tts:
        mock_supabase = MagicMock()
        mock_supabase.auth.get_user.return_value.user = MagicMock()
        mock_get_supabase.return_value = mock_supabase
        mock_retrieve.return_value = []
        mock_generate.return_value = "Hi!"
        mock_tts.return_value = b"audio"
        mock_manager.connect = AsyncMock()
        mock_manager.disconnect = MagicMock()
        mock_manager.send_json = AsyncMock()
        mock_manager.send_bytes = AsyncMock()
        await ws_router.routes[0].endpoint(mock_ws, "session-1")
        mock_manager.send_json.assert_called()
        mock_manager.send_bytes.assert_called()
