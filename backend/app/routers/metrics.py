from fastapi import APIRouter, HTTPException, status
from app.models.database import get_supabase
from app.models.schemas import CallMetric

router = APIRouter(prefix="/api/sessions", tags=["metrics"])


@router.get("/{session_id}/metrics", response_model=CallMetric | None)
async def get_session_metrics(session_id: str):
    supabase = get_supabase()
    session_res = supabase.table("sessions").select("id").eq("id", session_id).execute()
    if not session_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    res = supabase.table("call_metrics").select("*").eq("session_id", session_id).limit(1).execute()
    if res.data:
        return CallMetric(**res.data[0])
    return None