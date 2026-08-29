from fastapi import APIRouter, Depends
from app.models.database import get_supabase
from app.models.schemas import Analytics
from datetime import datetime, timedelta, timezone
from app.routers.auth import get_current_user

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("", response_model=Analytics)
async def get_analytics(user=Depends(get_current_user)):
    supabase = get_supabase()
    sessions_res = supabase.table("sessions").select("*", count="exact").execute()
    turns_res = supabase.table("turns").select("*").execute()

    total_sessions = sessions_res.count or 0
    turns = turns_res.data or []
    total_turns = len(turns)

    latencies = [t["latency_ms"] for t in turns if t.get("latency_ms") is not None]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    interruptions = sum(1 for t in turns if t.get("interrupted"))

    now = datetime.now(timezone.utc)
    recent = [s for s in (sessions_res.data or []) if datetime.fromisoformat(s["started_at"]) > now - timedelta(days=7)]
    avg_duration = 0.0
    if recent:
        durations = []
        for s in recent:
            if s.get("ended_at"):
                start = datetime.fromisoformat(s["started_at"])
                end = datetime.fromisoformat(s["ended_at"])
                durations.append((end - start).total_seconds())
        avg_duration = sum(durations) / len(durations) if durations else 0.0

    sentiments = {}
    for t in turns:
        s = t.get("sentiment") or "neutral"
        sentiments[s] = sentiments.get(s, 0) + 1

    return Analytics(
        total_sessions=total_sessions,
        total_turns=total_turns,
        avg_latency_ms=avg_latency,
        interruption_count=interruptions,
        avg_session_duration_s=avg_duration,
        sentiment_breakdown=sentiments,
    )