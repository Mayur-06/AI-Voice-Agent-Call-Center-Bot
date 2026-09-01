from fastapi import APIRouter, WebSocket
from app.websocket.handler import websocket_voice

router = APIRouter()
router.add_websocket_route("/ws/voice/{session_id}", websocket_voice)
