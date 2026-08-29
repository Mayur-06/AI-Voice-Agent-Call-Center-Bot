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
async def test_websocket_voice_connect_and_disconnect():
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