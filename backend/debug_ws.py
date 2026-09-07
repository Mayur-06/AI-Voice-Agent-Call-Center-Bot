import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import WebSocket

# First, let's see what happens when we import the handler
print("Importing handler...")
from app.websocket.handler import router as ws_router
print("Handler imported")

# Now let's simulate the test
mock_ws = AsyncMock(spec=WebSocket)
mock_ws.receive = AsyncMock(side_effect=[
    {"type": "websocket.disconnect"},
])

with patch("app.websocket.handler.manager") as mock_manager, \
     patch("app.websocket.handler.create_session", return_value="session-1"), \
     patch("app.websocket.handler.end_session", return_value=None), \
     patch("app.websocket.handler.get_persona_voice_id", return_value="en-IN-NeerjaNeural"), \
     patch("app.websocket.handler._get_default_persona_id", return_value="default"), \
     patch("app.websocket.handler._load_session", return_value=None):
    mock_manager.connect = AsyncMock()
    mock_manager.disconnect = MagicMock()
    mock_manager.send_json = AsyncMock()
    
    print("Calling endpoint...")
    try:
        asyncio.run(ws_router.routes[0].endpoint(mock_ws, "session-1"))
        print("Endpoint returned")
    except Exception as e:
        print(f"Error: {e}")
    
    print("Done")
