import uuid
from datetime import datetime, timezone
from app.models.database import get_supabase

_PERSONA_SLUG_MAP = {
    "customer-support": "Customer Support",
    "technical-expert": "Technical Expert",
    "sales-assistant": "Sales Assistant",
    "general-assistant": "General Assistant",
}


async def _get_default_persona_id() -> str:
    supabase = get_supabase()
    try:
        res = supabase.table("personas").select("id").eq("name", "default").limit(1).execute()
        if res.data:
            return res.data[0]["id"]
    except Exception:
        pass
    try:
        res = supabase.table("personas").select("id").limit(1).execute()
        if res.data:
            return res.data[0]["id"]
    except Exception:
        pass
    raise RuntimeError("No personas available")


async def resolve_persona_id(persona_id: str) -> str:
    if not persona_id:
        return await _get_default_persona_id()
    try:
        uuid.UUID(persona_id)
        return persona_id
    except ValueError:
        pass
    name = _PERSONA_SLUG_MAP.get(persona_id, persona_id)
    supabase = get_supabase()
    try:
        res = supabase.table("personas").select("id").eq("name", name).limit(1).execute()
        if res.data:
            return res.data[0]["id"]
    except Exception:
        pass
    return await _get_default_persona_id()


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
                    tts_first_audio_latency_ms: int | None = None,
                    recording_start_ms: int | None = None, recording_end_ms: int | None = None,
                    message_id: str | None = None):
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
        "recording_start_ms": recording_start_ms,
        "recording_end_ms": recording_end_ms,
    }
    if message_id:
        payload["id"] = message_id
    res = supabase.table("messages").insert(payload).execute()
    inserted = res.data[0] if isinstance(res.data, list) and res.data else {}
    return inserted.get("id")


async def load_turns(session_id: str) -> list[dict[str, str]]:
    supabase = get_supabase()
    res = supabase.table("messages").select("speaker,text").eq("session_id", session_id).order("sequence_number").execute()
    return [{"role": row["speaker"], "content": row["text"]} for row in (res.data or [])]


async def load_messages(session_id: str) -> list[dict]:
    supabase = get_supabase()
    res = supabase.table("messages").select("*").eq("session_id", session_id).order("sequence_number").execute()
    return res.data or []


async def load_session(session_id: str) -> dict | None:
    supabase = get_supabase()
    res = supabase.table("sessions").select("*").eq("id", session_id).limit(1).execute()
    if res.data:
        return res.data[0]
    return None


async def end_session(session_id: str, recording_url: str | None = None, summary: str | None = None):
    supabase = get_supabase()
    ended_at = datetime.now(timezone.utc).isoformat()

    session = await load_session(session_id)
    if not session:
        return

    started_at = session.get("started_at")
    duration = 0.0
    if started_at:
        try:
            start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
            duration = (end_dt - start_dt).total_seconds()
        except Exception:
            pass

    messages = await load_messages(session_id)
    user_turns = [m for m in messages if m.get("speaker") == "user"]
    assistant_turns = [m for m in messages if m.get("speaker") == "assistant"]
    turn_count = len(user_turns) + len(assistant_turns)

    user_speaking_time = 0.0
    agent_speaking_time = 0.0
    for m in messages:
        start = m.get("recording_start_ms")
        end = m.get("recording_end_ms")
        if start is not None and end is not None and end > start:
            ms = end - start
            if m.get("speaker") == "user":
                user_speaking_time += ms / 1000.0
            else:
                agent_speaking_time += ms / 1000.0

    latencies = [m["latency_ms"] for m in messages if m.get("latency_ms") is not None]
    average_latency = sum(latencies) / len(latencies) if latencies else 0.0

    sentiments = [m["sentiment"] for m in messages if m.get("sentiment")]
    sentiment_score = None
    resolution_status = "unknown"
    if sentiments:
        score_map = {"positive": 1.0, "neutral": 0.0, "negative": -0.5, "frustrated": -1.0}
        scores = [score_map.get(s, 0.0) for s in sentiments]
        sentiment_score = sum(scores) / len(scores)
        if sentiment_score >= 0.3:
            resolution_status = "resolved_positive"
        elif sentiment_score <= -0.6:
            resolution_status = "escalation_needed"
        else:
            resolution_status = "resolved"

    payload = {"ended_at": ended_at, "duration": duration, "status": "ended"}
    if recording_url:
        payload["recording_url"] = recording_url
    if summary:
        payload["summary"] = summary
    try:
        supabase.table("sessions").update(payload).eq("id", session_id).execute()
    except Exception:
        pass

    metrics_payload = {
        "session_id": session_id,
        "total_duration": duration,
        "user_speaking_time": user_speaking_time,
        "agent_speaking_time": agent_speaking_time,
        "turn_count": turn_count,
        "average_latency": average_latency,
        "sentiment_score": sentiment_score,
        "resolution_status": resolution_status,
    }
    try:
        supabase.table("call_metrics").upsert(metrics_payload, on_conflict="session_id").execute()
    except Exception:
        pass
