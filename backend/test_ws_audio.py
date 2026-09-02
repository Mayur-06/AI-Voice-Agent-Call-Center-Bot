import asyncio
import json
import uuid
from pathlib import Path

import httpx
import websockets


BASE_URL = "http://127.0.0.1:8000"


async def create_persona() -> dict:
    payload = {
        "name": "Audio Test Persona",
        "description": "Audio test",
        "system_prompt": "You are a helpful voice assistant.",
        "voice_id": "en-IN-NeerjaNeural",
        "domain": "testing",
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{BASE_URL}/api/personas/", json=payload)
        r.raise_for_status()
        return r.json()


async def create_session(persona_id: str) -> dict:
    payload = {
        "persona_id": persona_id,
        "status": "active",
        "selected_voice": "en-IN-NeerjaNeural",
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{BASE_URL}/api/sessions", json=payload)
        r.raise_for_status()
        return r.json()


async def run(session_id: str, out_dir: Path):
    out_dir.mkdir(exist_ok=True)
    uri = f"ws://127.0.0.1:8000/ws/voice/{session_id}"
    async with websockets.connect(uri) as ws:
        print("[WS] connected")

        await ws.send(json.dumps({
            "type": "auth",
            "persona_id": "default",
            "voice_id": "en-IN-NeerjaNeural",
        }))
        print("[WS] sent auth")
        print("[WS] recv:", await ws.recv())

        await ws.send(json.dumps({
            "type": "transcript",
            "text": "Please respond with a short greeting only.",
        }))
        print("[WS] sent transcript")

        chunk_index = 0
        try:
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=30)
                if isinstance(msg, str):
                    data = json.loads(msg)
                    print("[WS] JSON:", data)
                    if data.get("type") == "response_ready":
                        print("[WS] response_ready received, done")
                        break
                else:
                    chunk_index += 1
                    path = out_dir / f"chunk_{chunk_index:03d}.bin"
                    path.write_bytes(msg)
                    print(f"[WS] BINARY chunk {chunk_index}: {len(msg)} bytes -> {path}")
        except asyncio.TimeoutError:
            print("[WS] timeout")

    print(f"[WS] saved {chunk_index} audio chunks to {out_dir}")


async def main():
    print("[1] Creating persona...")
    persona = await create_persona()
    persona_id = persona["id"]
    print("Persona:", persona_id)

    print("[2] Creating session...")
    session = await create_session(persona_id)
    session_id = session["id"]
    print("Session:", session_id)

    print("[3] Opening WebSocket...")
    await run(session_id, Path("backend/ws_audio_chunks"))


if __name__ == "__main__":
    asyncio.run(main())