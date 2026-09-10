from fastapi import APIRouter, HTTPException, status
from app.models.database import get_supabase
from app.models.schemas import SentimentRecord
from typing import List

router = APIRouter(prefix="/api/sessions", tags=["sentiment"])


@router.get("/{session_id}/sentiment", response_model=List[SentimentRecord])
async def get_session_sentiment(session_id: str):
    supabase = get_supabase()
    session_res = supabase.table("sessions").select("id").eq("id", session_id).execute()
    if not session_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    res = supabase.table("sentiment_records").select("*").eq("session_id", session_id).order("created_at").execute()
    return [SentimentRecord(**row) for row in (res.data or [])]