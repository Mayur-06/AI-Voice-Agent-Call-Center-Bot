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
