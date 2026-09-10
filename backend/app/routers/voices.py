from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from app.models.database import get_supabase, run_supabase
from app.models.schemas import Voice
from app.services.tts import synthesize_speech
from typing import List

router = APIRouter(prefix="/api/voices", tags=["voices"])

_VOICES = [
    {
        "voice_id": "en-IN-NeerjaNeural",
        "name": "Neerja (Female, India)",
        "language": "en-IN",
        "preview_url": "https://res.cloudinary.com/ejpx0qht/video/upload/v1788860561/voice-previews/en-IN-NeerjaNeural.mp3",
    },
    {
        "voice_id": "en-US-JennyNeural",
        "name": "Jenny (Female, US)",
        "language": "en-US",
        "preview_url": "https://res.cloudinary.com/ejpx0qht/video/upload/v1788860562/voice-previews/en-US-JennyNeural.mp3",
    },
]

_VOICE_PREVIEW_TEXTS = {
    "en-IN-NeerjaNeural": "Hello! I am Neerja, your voice assistant.",
    "en-US-JennyNeural": "Hello! I am Jenny, your voice assistant.",
}


async def _ensure_voices():
    supabase = get_supabase()
    try:
        existing = await run_supabase(
            lambda: supabase.table("voices").select("voice_id").execute()
        )
        existing_ids = {row["voice_id"] for row in (existing.data or [])}
        for v in _VOICES:
            if v["voice_id"] in existing_ids:
                await run_supabase(
                    lambda v=v: supabase.table("voices")
                    .update({"preview_url": v.get("preview_url")})
                    .eq("voice_id", v["voice_id"])
                    .execute()
                )
            else:
                await run_supabase(
                    lambda v=v: supabase.table("voices").insert(v).execute()
                )
    except Exception:
        pass


@router.get("", response_model=List[Voice])
async def get_voices():
    await _ensure_voices()
    supabase = get_supabase()
    res = supabase.table("voices").select("*").order("id").execute()
    return [Voice(**row) for row in (res.data or [])]


@router.get("/{voice_id}/preview")
async def preview_voice(voice_id: str):
    voice = next((v for v in _VOICES if v["voice_id"] == voice_id), None)
    if not voice:
        raise HTTPException(status_code=404, detail="Voice not found")

    preview_text = _VOICE_PREVIEW_TEXTS.get(voice["voice_id"], "Hello! I am your voice assistant.")
    audio_bytes = await synthesize_speech(preview_text, voice["voice_id"])
    return Response(content=audio_bytes, media_type="audio/mpeg")
