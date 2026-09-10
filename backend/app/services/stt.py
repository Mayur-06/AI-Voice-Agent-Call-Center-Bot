import re
import httpx
from app.config import settings


GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


async def transcribe_audio(audio_bytes: bytes, language: str = "en") -> str:
    async with httpx.AsyncClient() as client:
        files = {"file": ("audio.wav", audio_bytes, "audio/wav")}
        data = {
            "model": "whisper-large-v3-turbo",
            "language": language,
            "response_format": "json",
        }
        headers = {"Authorization": f"Bearer {settings.groq_api_key}"}
        response = await client.post(GROQ_STT_URL, files=files, data=data, headers=headers, timeout=30.0)
        response.raise_for_status()
        result = response.json()
        return result.get("text", "")


def is_noisy_transcription(text: str) -> bool:
    if not text:
        return True
    stripped = text.strip()
    if len(stripped) < 2:
        return True
    alphabetic = sum(c.isalpha() for c in stripped)
    if alphabetic / max(len(stripped), 1) < 0.5:
        return True
    return False
