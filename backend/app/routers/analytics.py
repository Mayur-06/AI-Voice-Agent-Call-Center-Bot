from fastapi import APIRouter
from datetime import datetime, timezone, timedelta
from app.models.database import get_supabase

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("")
async def get_analytics():
    supabase = get_supabase()
    now = datetime.now(timezone.utc)

    sessions = supabase.table("sessions").select("*").execute().data or []
    messages = supabase.table("messages").select("latency_ms, sentiment, interrupted, speaker, timestamp, session_id").execute().data or []
    call_metrics = supabase.table("call_metrics").select("*").execute().data or []
    sentiment_records = supabase.table("sentiment_records").select("*").execute().data or []
    personas = supabase.table("personas").select("id, name").execute().data or []

    persona_map = {str(p["id"]): p.get("name", "Unknown") for p in personas}

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
                start_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(ended.replace("Z", "+00:00"))
                durations.append((end_dt - start_dt).total_seconds())
            except Exception:
                pass
    avg_duration = sum(durations) / len(durations) if durations else 0

    calls_over_time: dict[str, int] = {}
    for s in sessions:
        started = s.get("started_at")
        if not started:
            continue
        try:
            dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
            key = dt.strftime("%Y-%m-%d")
            calls_over_time[key] = calls_over_time.get(key, 0) + 1
        except Exception:
            pass
    calls_over_time_list = [{"date": k, "count": v} for k, v in sorted(calls_over_time.items())]

    per_persona = {}
    for s in sessions:
        pid = str(s.get("persona_id", ""))
        name = persona_map.get(pid, "Unknown")
        per_persona.setdefault(name, {"sessions": 0, "total_latency": 0.0, "latency_count": 0, "durations": []})
        per_persona[name]["sessions"] += 1
        started = s.get("started_at")
        ended = s.get("ended_at")
        if started and ended:
            try:
                start_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(ended.replace("Z", "+00:00"))
                per_persona[name]["durations"].append((end_dt - start_dt).total_seconds())
            except Exception:
                pass
    for m in messages:
        pid = ""
        for s in sessions:
            if str(s.get("id")) == str(m.get("session_id", "")):
                pid = str(s.get("persona_id", ""))
                break
        name = persona_map.get(pid, "Unknown")
        if name in per_persona and m.get("latency_ms") is not None:
            per_persona[name]["total_latency"] += m["latency_ms"]
            per_persona[name]["latency_count"] += 1

    per_persona_stats = []
    for name, stats in per_persona.items():
        per_persona_stats.append({
            "persona": name,
            "sessions": stats["sessions"],
            "avg_latency_ms": round(stats["total_latency"] / stats["latency_count"], 2) if stats["latency_count"] else 0,
            "avg_duration_s": round(sum(stats["durations"]) / len(stats["durations"]), 2) if stats["durations"] else 0,
        })

    result = {
        "total_sessions": total_sessions,
        "total_messages": total_messages,
        "avg_latency_ms": round(avg_latency, 2),
        "avg_session_duration_s": round(avg_duration, 2),
        "sentiment_breakdown": sentiment_breakdown,
        "interruption_count": sum(1 for m in messages if m.get("interrupted")),
        "anomalies": [],
        "calls_over_time": calls_over_time_list,
        "per_persona_stats": per_persona_stats,
    }
    return result