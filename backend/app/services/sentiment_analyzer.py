from app.orchestration.graphs import sentiment_graph
from app.models.database import get_supabase
from datetime import datetime, timezone


async def analyze_sentiment(user_text: str) -> str:
    result = await sentiment_graph.ainvoke({"text": user_text, "retries": 0})
    return result.get("sentiment", "neutral")


async def save_sentiment(session_id: str, message_id: str, sentiment: str) -> None:
    score_map = {"positive": 1.0, "neutral": 0.0, "negative": -0.5, "frustrated": -1.0}
    score = score_map.get(sentiment, 0.0)
    supabase = get_supabase()
    try:
        supabase.table("sentiment_records").insert({
            "session_id": session_id,
            "message_id": message_id,
            "sentiment": sentiment,
            "score": score,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception:
        pass
