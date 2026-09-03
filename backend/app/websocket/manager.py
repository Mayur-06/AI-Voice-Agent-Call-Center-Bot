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
        self.recording_enabled: Dict[str, bool] = {}
        self.ai_audio_buffers: Dict[str, bytearray] = {}
        self.ai_audio_segments: Dict[str, list[dict]] = {}
        self.ai_audio_current_start: Dict[str, int] = {}

    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[session_id] = websocket
        self.recording_enabled[session_id] = False
        self.ai_audio_buffers[session_id] = bytearray()
        self.ai_audio_segments[session_id] = []
        self.ai_audio_current_start[session_id] = 0

    def disconnect(self, session_id: str):
        if session_id in self.active_connections:
            del self.active_connections[session_id]
        if session_id in self.recording_enabled:
            del self.recording_enabled[session_id]
        if session_id in self.ai_audio_buffers:
            del self.ai_audio_buffers[session_id]
        if session_id in self.ai_audio_segments:
            del self.ai_audio_segments[session_id]
        if session_id in self.ai_audio_current_start:
            del self.ai_audio_current_start[session_id]

    def enable_recording(self, session_id: str) -> None:
        self.recording_enabled[session_id] = True
        self.ai_audio_buffers[session_id] = bytearray()
        self.ai_audio_segments[session_id] = []
        self.ai_audio_current_start[session_id] = 0

    def start_ai_segment(self, session_id: str, start_ms: int) -> None:
        if not self.recording_enabled.get(session_id):
            return
        self.ai_audio_current_start[session_id] = start_ms
        self.ai_audio_buffers[session_id] = bytearray()

    def append_ai_audio(self, session_id: str, data: bytes) -> None:
        if not self.recording_enabled.get(session_id):
            return
        self.ai_audio_buffers[session_id].extend(data)

    def finish_ai_segment(self, session_id: str, end_ms: int) -> dict | None:
        if not self.recording_enabled.get(session_id):
            return None
        buf = bytes(self.ai_audio_buffers.get(session_id, bytearray()))
        if not buf:
            return None
        start_ms = self.ai_audio_current_start.get(session_id, 0)
        seg = {
            "start_ms": start_ms,
            "end_ms": end_ms,
            "duration_ms": max(end_ms - start_ms, 0),
            "pcm": buf,
        }
        segs = self.ai_audio_segments.setdefault(session_id, [])
        segs.append(seg)
        self.ai_audio_buffers[session_id] = bytearray()
        return seg

    def get_ai_segments(self, session_id: str) -> list[dict]:
        return list(self.ai_audio_segments.get(session_id, []))

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
