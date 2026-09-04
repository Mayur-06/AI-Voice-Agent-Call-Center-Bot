import asyncio
import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs" / "call_sessions"
SESSION_LOG_MAX = 2000

session_log_queues: dict[str, deque[dict]] = {}
session_log_events: dict[str, list[asyncio.Event]] = {}
session_log_locks: dict[str, asyncio.Lock] = {}


def _ensure_log_dir() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _log_path(session_id: str) -> Path:
    return LOG_DIR / f"{session_id}.log"


def _format_entry(entry: dict) -> str:
    ts = entry.get("ts", datetime.now(timezone.utc).isoformat())
    level = entry.get("level", "info")
    msg = entry.get("msg", "")
    return f"{ts} [{level.upper()}] {msg}"


async def _write_entry(session_id: str, entry: dict) -> None:
    if session_id in session_log_queues:
        lock = session_log_locks[session_id]
    else:
        _ensure_log_dir()
        lock = asyncio.Lock()
        session_log_queues[session_id] = deque(maxlen=SESSION_LOG_MAX)
        session_log_locks[session_id] = lock

    async with lock:
        session_log_queues[session_id].append(entry)

        try:
            path = _log_path(session_id)
            line = _format_entry(entry)
            await asyncio.to_thread(_append_line_to_file, path, line)
        except Exception:
            pass

    for ev in list(session_log_events.get(session_id, [])):
        ev.set()


def _append_line_to_file(path: Path, line: str) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)
        f.write("\n")


async def append_log(session_id: str, entry: dict) -> None:
    if "ts" not in entry:
        entry = {**entry, "ts": datetime.now(timezone.utc).isoformat()}
    await _write_entry(session_id, entry)


def get_logs(session_id: str) -> list[dict]:
    dq = session_log_queues.get(session_id)
    return list(dq) if dq else []


async def stream_logs(session_id: str):
    ev = asyncio.Event()
    session_log_events.setdefault(session_id, []).append(ev)
    try:
        for entry in get_logs(session_id):
            yield f"data: {json.dumps(entry)}\n\n"
        while True:
            await ev.wait()
            ev.clear()
            for entry in get_logs(session_id)[:]:
                yield f"data: {json.dumps(entry)}\n\n"
    finally:
        session_log_events.get(session_id, []).remove(ev)


async def close_session(session_id: str) -> None:
    session_log_queues.pop(session_id, None)
    session_log_events.pop(session_id, None)
    session_log_locks.pop(session_id, None)
