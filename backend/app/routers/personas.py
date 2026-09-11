from fastapi import APIRouter, HTTPException, status
from app.models.database import get_supabase, run_supabase
from app.models.schemas import PersonaCreate, Persona
from typing import List
import uuid
from datetime import datetime, timezone

router = APIRouter(prefix="/api/personas", tags=["personas"])

_DEFAULT_PERSONAS = [
    {
        "name": "Neha",
        "description": "Empathetic, patient and solution-oriented support agent.",
        "system_prompt": "You are a warm, patient customer support agent. Prioritize empathy, clarity and resolution. Keep responses conversational and actionable. When uncertain, offer the next best step rather than guessing.",
        "domain": "support",
        "avatar_url": "https://res.cloudinary.com/ejpx0qht/image/upload/v1788858004/aura-avatars/neha.png",
    },
    {
        "name": "Alena",
        "description": "Precise, knowledgeable technical advisor.",
        "system_prompt": "You are a precise technical expert. Answer with accurate, step-by-step guidance. Use concise technical language, define terms when needed, and provide troubleshooting paths that the user can follow immediately.",
        "domain": "technical",
        "avatar_url": "https://res.cloudinary.com/ejpx0qht/image/upload/v1788858005/aura-avatars/alena.png",
    },
    {
        "name": "Sora",
        "description": "Friendly, persuasive sales assistant.",
        "system_prompt": "You are a friendly, persuasive sales assistant. Highlight benefits, match features to user needs, keep momentum, and make next steps easy. Avoid pushy language and stay concise.",
        "domain": "sales",
        "avatar_url": "https://res.cloudinary.com/ejpx0qht/image/upload/v1788858006/aura-avatars/sora.png",
    },
    {
        "name": "Aria",
        "description": "Balanced, helpful general-purpose assistant.",
        "system_prompt": "You are a balanced, helpful general assistant. Adapt to the user's intent, keep answers useful and concise, and ask clarifying questions when needed. Be direct, organized and supportive.",
        "domain": "general",
        "avatar_url": "https://res.cloudinary.com/ejpx0qht/image/upload/v1788858007/aura-avatars/aria.png",
    },
]


def _persona_row(payload: dict) -> dict:
    return {
        "id": payload.get("id", str(uuid.uuid4())),
        "name": payload["name"],
        "description": payload.get("description"),
        "system_prompt": payload["system_prompt"],
        "voice_id": payload.get("voice_id", "en-IN-NeerjaNeural"),
        "domain": payload.get("domain"),
        "avatar_url": payload.get("avatar_url"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


async def _ensure_personas():
    supabase = get_supabase()
    rows = [_persona_row(p) for p in _DEFAULT_PERSONAS]
    try:
        for row in rows:
            existing = await run_supabase(lambda: supabase.table("personas").select("id").eq("name", row["name"]).limit(1).execute())
            if existing.data:
                # _persona_row() mints a new uuid every call. Sending it in an
                # UPDATE tried to rewrite the primary key and returned 409 on
                # every GET /api/personas, so seeded rows never refreshed.
                update_row = {k: v for k, v in row.items() if k not in ("id", "created_at")}
                await run_supabase(lambda: supabase.table("personas").update(update_row).eq("id", existing.data[0]["id"]).execute())
            else:
                await run_supabase(lambda: supabase.table("personas").insert(row).execute())
    except Exception:
        pass


@router.get("", response_model=List[Persona])
async def list_personas():
    await _ensure_personas()
    supabase = get_supabase()
    res = await run_supabase(lambda: supabase.table("personas").select("*").order("name").execute())
    return [Persona(**row) for row in (res.data or [])]


@router.post("", response_model=Persona, status_code=status.HTTP_201_CREATED)
async def create_persona(persona_data: PersonaCreate):
    supabase = get_supabase()
    payload = _persona_row(persona_data.model_dump())
    res = await run_supabase(lambda: supabase.table("personas").insert(payload).execute())
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to create persona")
    return Persona(**res.data[0])
