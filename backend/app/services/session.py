import uuid
from datetime import datetime, timezone
from app.models.database import get_supabase


async def create_session(
    persona_id: str,
    user_id: str | None = None,
    metadata: dict | None = None,
    session_id: str | None = None,
    status: str = "active",
    selected_voice: str | None = None,
) -> str:
    supabase = get_supabase()

    if session_id:
        existing = supabase.table("sessions").select("id").eq("id", session_id).execute()
        if existing.data:
            return existing.data[0]["id"]

    resolved_user_id = user_id or str(uuid.uuid4())

    payload = {
        "persona_id": persona_id,
        "user_id": resolved_user_id,
        "status": status,
        "selected_voice": selected_voice,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    if session_id:
        payload["id"] = session_id
    res = supabase.table("sessions").insert(payload).execute()
    return res.data[0]["id"]


async def save_turn(session_id: str, speaker: str, text: str, sentiment: str | None = None,
                    latency_ms: int | None = None, interrupted: bool = False,
                    stt_latency_ms: int | None = None, llm_latency_ms: int | None = None,
                    tts_first_audio_latency_ms: int | None = None):
    supabase = get_supabase()
    seq = 0
    try:
        existing = supabase.table("messages").select("sequence_number").eq("session_id", session_id).order("sequence_number", desc=True).limit(1).execute()
        if existing.data:
            seq = existing.data[0]["sequence_number"] + 1
    except Exception:
        pass
    payload = {
        "session_id": session_id,
        "speaker": speaker,
        "text": text,
        "sentiment": sentiment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "latency_ms": latency_ms,
        "interrupted": interrupted,
        "sequence_number": seq,
        "stt_latency_ms": stt_latency_ms,
        "llm_latency_ms": llm_latency_ms,
        "tts_first_audio_latency_ms": tts_first_audio_latency_ms,
    }
    supabase.table("messages").insert(payload).execute()


async def load_turns(session_id: str) -> list[dict[str, str]]:
    supabase = get_supabase()
    res = supabase.table("messages").select("speaker,text").eq("session_id", session_id).order("sequence_number").execute()
    return [{"role": row["speaker"], "content": row["text"]} for row in (res.data or [])]


async def end_session(session_id: str, recording_url: str | None = None, summary: str | None = None):
    supabase = get_supabase()
    payload = {"ended_at": datetime.now(timezone.utc).isoformat()}
    supabase.table("sessions").update(payload).eq("id", session_id).execute()
