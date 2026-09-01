from datetime import datetime, timezone
from app.models.database import get_supabase
from app.config import settings


async def create_session(persona_id: str, metadata: dict | None = None, session_id: str | None = None) -> str:
    supabase = get_supabase()

    if session_id:
        existing = supabase.table("sessions").select("id").eq("id", session_id).execute()
        if existing.data:
            return existing.data[0]["id"]

    payload = {
        "persona_id": persona_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    if session_id:
        payload["id"] = session_id
    res = supabase.table("sessions").insert(payload).execute()
    return res.data[0]["id"]


async def save_turn(session_id: str, speaker: str, text: str, sentiment: str | None = None,
                    latency_ms: int | None = None, interrupted: bool = False):
    supabase = get_supabase()
    supabase.table("messages").insert({
        "session_id": session_id,
        "speaker": speaker,
        "text": text,
        "sentiment": sentiment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "latency_ms": latency_ms,
        "interrupted": interrupted,
        "sequence_number": 0,
    }).execute()


async def end_session(session_id: str, recording_url: str | None = None, summary: str | None = None):
    supabase = get_supabase()
    payload = {"ended_at": datetime.now(timezone.utc).isoformat()}
    supabase.table("sessions").update(payload).eq("id", session_id).execute()
