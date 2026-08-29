from datetime import datetime
from app.models.database import get_supabase


async def create_session(persona_id: str, user_id: str | None = None, metadata: dict | None = None) -> str:
    supabase = get_supabase()
    res = supabase.table("sessions").insert({
        "persona_id": persona_id,
        "user_id": user_id,
        "metadata": metadata or {},
        "started_at": datetime.utcnow().isoformat(),
    }).execute()
    return res.data[0]["id"]


async def save_turn(session_id: str, speaker: str, text: str, sentiment: str | None = None,
                    latency_ms: int | None = None, interrupted: bool = False):
    supabase = get_supabase()
    supabase.table("turns").insert({
        "session_id": session_id,
        "speaker": speaker,
        "text": text,
        "sentiment": sentiment,
        "timestamp": datetime.utcnow().isoformat(),
        "latency_ms": latency_ms,
        "interrupted": interrupted,
    }).execute()


async def end_session(session_id: str):
    supabase = get_supabase()
    supabase.table("sessions").update({"ended_at": datetime.utcnow().isoformat()}).eq("id", session_id).execute()
