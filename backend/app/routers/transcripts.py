from fastapi import APIRouter, HTTPException, status
from app.models.database import get_supabase
from app.models.schemas import Message
from typing import List

router = APIRouter(prefix="/api/sessions", tags=["transcripts"])


@router.get("/{session_id}/transcript", response_model=List[Message])
async def get_session_transcript(session_id: str):
    supabase = get_supabase()
    session_res = supabase.table("sessions").select("id").eq("id", session_id).execute()
    if not session_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    res = supabase.table("messages").select("*").eq("session_id", session_id).order("sequence_number").execute()
    return [Message(**row) for row in (res.data or [])]