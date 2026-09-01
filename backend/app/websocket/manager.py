import asyncio
import json
from collections import deque
from typing import Dict
from fastapi import WebSocket


SESSION_LOG_MAX = 200
session_logs: dict[str, deque[dict]] = {}
session_log_events: dict[str, list[asyncio.Event]] = {}


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[session_id] = websocket

    def disconnect(self, session_id: str):
        if session_id in self.active_connections:
            del self.active_connections[session_id]

    async def send_json(self, session_id: str, message: dict):
        if session_id in self.active_connections:
            await self.active_connections[session_id].send_json(message)

    async def send_bytes(self, session_id: str, data: bytes):
        if session_id in self.active_connections:
            await self.active_connections[session_id].send_bytes(data)


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


manager = ConnectionManager()
