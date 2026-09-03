from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response, FileResponse
from app.models.database import get_supabase, get_supabase_admin
import os

router = APIRouter(prefix="/api/sessions", tags=["recordings"])


@router.get("/{session_id}/recording")
async def get_session_recording(session_id: str):
    supabase = get_supabase()
    session_res = supabase.table("sessions").select("*").eq("id", session_id).execute()
    if not session_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    session = session_res.data[0]
    recording_path = session.get("recording_url")
    if recording_path:
        try:
            storage = get_supabase_admin().storage.from_("recordings")
            file_data = storage.download(recording_path)
            return Response(content=file_data, media_type="audio/wav")
        except Exception:
            pass

    local_path = os.path.join("recordings", f"{session_id}.wav")
    if os.path.exists(local_path):
        return FileResponse(local_path, media_type="audio/wav")

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")