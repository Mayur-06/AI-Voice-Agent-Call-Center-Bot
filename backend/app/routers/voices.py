import logging
import httpx
from fastapi import APIRouter, HTTPException
from app.models.schemas import Voice
from app.config import settings
from edge_tts import list_voices

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voices", tags=["voices"])

_FALLBACK_VOICES = [
    Voice(voice_id="en-IN-NeerjaNeural", name="Neerja", category="premade", preview_url=None),
    Voice(voice_id="en-US-GuyNeural", name="Guy", category="premade", preview_url=None),
    Voice(voice_id="en-GB-SoniaNeural", name="Sonia", category="premade", preview_url=None),
]


@router.get("", response_model=list[Voice])
async def list_voices():
    try:
        voices_data = await list_voices()
        voices = []
        for v in voices_data:
            voices.append(Voice(
                voice_id=v.get("ShortName", ""),
                name=v.get("FriendlyName", v.get("Name", "")),
                category="premade" if v.get("Status") == "GA" else "custom",
                preview_url=None,
            ))
        if voices:
            return voices
    except Exception as exc:
        logger.warning("Failed to fetch voices from Edge TTS: %s", exc)

    logger.info("Falling back to default voice list")
    return _FALLBACK_VOICES
