import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import MagicMock, AsyncMock
from app.websocket.manager import ConnectionManager


@pytest.mark.asyncio
async def test_connect_and_disconnect():
    manager = ConnectionManager()
    mock_ws = AsyncMock()
    await manager.connect("session-1", mock_ws)
    assert "session-1" in manager.active_connections
    manager.disconnect("session-1")
    assert "session-1" not in manager.active_connections


@pytest.mark.asyncio
async def test_send_json():
    manager = ConnectionManager()
    mock_ws = AsyncMock()
    await manager.connect("session-1", mock_ws)
    await manager.send_json("session-1", {"type": "status", "message": "ok"})
    mock_ws.send_json.assert_called_once_with({"type": "status", "message": "ok"})


@pytest.mark.asyncio
async def test_send_bytes():
    manager = ConnectionManager()
    mock_ws = AsyncMock()
    await manager.connect("session-1", mock_ws)
    await manager.send_bytes("session-1", b"audio-data")
    mock_ws.send_bytes.assert_called_once_with(b"audio-data")


@pytest.mark.asyncio
async def test_send_to_missing_session():
    manager = ConnectionManager()
    await manager.send_json("missing", {"type": "status"})
    await manager.send_bytes("missing", b"data")
