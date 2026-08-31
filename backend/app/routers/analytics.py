from fastapi import APIRouter
from datetime import datetime, timezone, timedelta
from app.models.database import get_supabase
from app.orchestration.graphs import insights_graph

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/")
async def get_analytics():
    supabase = get_supabase()
    now = datetime.now(timezone.utc)

    sessions = supabase.table("sessions").select("*").execute().data or []
    messages = supabase.table("messages").select("latency_ms, sentiment, interrupted").execute().data or []

    result = await insights_graph.ainvoke({"sessions": sessions, "messages": messages})
    insights = result.get("insights", {})

    if not insights:
        total_sessions = len(sessions)
        total_messages = len(messages)
        latencies = [m["latency_ms"] for m in messages if m.get("latency_ms") is not None]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        sentiments = [m["sentiment"] for m in messages if m.get("sentiment")]
        sentiment_breakdown = {s: sentiments.count(s) for s in set(sentiments) if s}
        durations = []
        for s in sessions:
            started = s.get("started_at")
            ended = s.get("ended_at")
            if started and ended:
                try:
                    start_dt = datetime.fromisoformat(started)
                    end_dt = datetime.fromisoformat(ended)
                    durations.append((end_dt - start_dt).total_seconds())
                except Exception:
                    pass
        avg_duration = sum(durations) / len(durations) if durations else 0
        insights = {
            "total_sessions": total_sessions,
            "total_messages": total_messages,
            "avg_latency_ms": round(avg_latency, 2),
            "avg_session_duration_s": round(avg_duration, 2),
            "sentiment_breakdown": sentiment_breakdown,
            "interruption_count": sum(1 for m in messages if m.get("interrupted")),
            "anomalies": [],
        }

    return insights
