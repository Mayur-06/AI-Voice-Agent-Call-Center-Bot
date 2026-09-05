import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import WebSocket

from app.websocket.handler import router as ws_router

async def main():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.receive = AsyncMock(side_effect=[
        {"text": '{"type": "stop_playback"}'},
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
        
        print("Calling endpoint...")
        try:
            await asyncio.wait_for(ws_router.routes[0].endpoint(mock_ws, "session-1"), timeout=5)
            print("Endpoint returned")
        except asyncio.TimeoutError:
            print("TIMEOUT!")
        except Exception as e:
            import traceback
            traceback.print_exc()
        
        print("Done")

asyncio.run(main())
