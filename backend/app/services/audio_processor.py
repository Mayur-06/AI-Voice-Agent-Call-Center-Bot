import os
import struct
import wave
from io import BytesIO
from app.services.audio import pcm_to_wav


async def save_session_recording(session_id: str, audio_buffer: bytes):
    os.makedirs("recordings", exist_ok=True)
    file_path = f"recordings/{session_id}.wav"

    try:
        wav_bytes = pcm_to_wav(audio_buffer)
    except Exception as exc:
        raise RuntimeError(f"Failed to encode session recording to WAV: {exc}") from exc

    with open(file_path, "wb") as f:
        f.write(wav_bytes)
    return file_path
