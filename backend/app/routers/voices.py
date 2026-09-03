from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from app.models.database import get_supabase
from app.models.schemas import Voice
from app.services.tts import synthesize_speech
from typing import List

router = APIRouter(prefix="/api/voices", tags=["voices"])

_VOICES = [
    {
        "voice_id": "en-IN-NeerjaNeural",
        "name": "Neerja (Female, India)",
        "language": "en-IN",
    },
    {
        "voice_id": "en-IN-PrabhatNeural",
        "name": "Prabhat (Male, India)",
        "language": "en-IN",
    },
]

_VOICE_PREVIEW_TEXTS = {
    "en-IN-NeerjaNeural": "Hello! I am Neerja, your voice assistant.",
    "en-IN-PrabhatNeural": "Hello! I am Prabhat, your voice assistant.",
}


async def _ensure_voices():
    supabase = get_supabase()
    try:
        res = supabase.table("voices").select("id").limit(1).execute()
        if res.data:
            return
    except Exception:
        return
    try:
        supabase.table("voices").insert(_VOICES).execute()
    except Exception:
        pass


@router.get("/", response_model=List[Voice])
async def get_voices():
    await _ensure_voices()
    supabase = get_supabase()
    res = supabase.table("voices").select("*").order("id").execute()
    return [Voice(**row) for row in (res.data or [])]


@router.get("/{voice_id}/preview")
async def preview_voice(voice_id: str):
    voice = next((v for v in _VOICES if v["voice_id"] == voice_id or v["id"] == voice_id), None)
    if not voice:
        raise HTTPException(status_code=404, detail="Voice not found")

    preview_text = _VOICE_PREVIEW_TEXTS.get(voice["voice_id"], "Hello! I am your voice assistant.")
    audio_bytes = await synthesize_speech(preview_text, voice["voice_id"])
    return Response(content=audio_bytes, media_type="audio/mpeg")
