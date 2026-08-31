from fastapi import APIRouter, HTTPException, status
from app.models.database import get_supabase
from app.models.schemas import SessionCreate, Session, MessageRequest, Message, Analytics
from app.services.llm import generate_response
from app.services.session import save_turn
from datetime import datetime
from typing import List

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", response_model=Session)
async def create_session(data: SessionCreate):
    supabase = get_supabase()
    res = supabase.table("sessions").insert({
        "persona_id": data.persona_id,
        "started_at": datetime.utcnow().isoformat(),
    }).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to create session")
    return Session(**res.data[0])


@router.get("")
async def list_sessions():
    supabase = get_supabase()
    res = supabase.table("sessions").select("*").order("started_at", desc=True).execute()
    return res.data or []


@router.get("/{session_id}")
async def get_session_details(session_id: str):
    supabase = get_supabase()
    res = (
        supabase.table("sessions")
        .select("*, messages(*)")
        .eq("id", session_id)
        .execute()
    )

    if not res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    return res.data[0]


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    supabase = get_supabase()
    supabase.table("messages").delete().eq("session_id", session_id).execute()
    supabase.table("sessions").delete().eq("id", session_id).execute()
    return {"status": "deleted"}


@router.post("/{session_id}/message")
async def send_message(session_id: str, data: MessageRequest):
    supabase = get_supabase()
    session_check = supabase.table("sessions").select("id").eq("id", session_id).execute()
    if not session_check.data:
        raise HTTPException(status_code=404, detail="Session not found")

    user_text = data.text or ""
    await save_turn(session_id, "user", user_text)

    conversation = [{"role": "user", "content": user_text}]
    response_text = await generate_response(conversation, "You are a helpful voice assistant.")
    await save_turn(session_id, "assistant", response_text)

    return {"session_id": session_id, "text": response_text}


@router.get("/{session_id}/transcript", response_model=List[Message])
async def get_transcript(session_id: str):
    supabase = get_supabase()
    session_check = supabase.table("sessions").select("id").eq("id", session_id).execute()
    if not session_check.data:
        raise HTTPException(status_code=404, detail="Session not found")
    res = supabase.table("messages").select("*").eq("session_id", session_id).order("timestamp").execute()
    return [Message(**m) for m in res.data]


@router.get("/{session_id}/summary")
async def get_summary(session_id: str):
    supabase = get_supabase()
    session_check = supabase.table("sessions").select("id").eq("id", session_id).execute()
    if not session_check.data:
        raise HTTPException(status_code=404, detail="Session not found")
    res = supabase.table("messages").select("*").eq("session_id", session_id).execute()
    return {"session_id": session_id, "summary": "Summary not yet implemented"}


@router.get("/{session_id}/sentiment")
async def get_sentiment(session_id: str):
    supabase = get_supabase()
    session_check = supabase.table("sessions").select("id").eq("id", session_id).execute()
    if not session_check.data:
        raise HTTPException(status_code=404, detail="Session not found")
    res = supabase.table("messages").select("sentiment,timestamp").eq("session_id", session_id).execute()
    return {"session_id": session_id, "sentiment_timeline": res.data}


@router.get("/{session_id}/metrics")
async def get_metrics(session_id: str):
    supabase = get_supabase()
    session_check = supabase.table("sessions").select("id").eq("id", session_id).execute()
    if not session_check.data:
        raise HTTPException(status_code=404, detail="Session not found")
    res = supabase.table("messages").select("latency_ms,interrupted").eq("session_id", session_id).execute()
    messages = res.data
    if not messages:
        return {
            "session_id": session_id,
            "metrics": {
                "turns_count": 0,
                "avg_latency_ms": 0,
                "interruptions": 0,
                "note": "No messages yet. Send a message or start a voice conversation to generate metrics.",
            },
        }
    latencies = [m["latency_ms"] for m in messages if m.get("latency_ms") is not None]
    interruptions = sum(1 for m in messages if m.get("interrupted"))
    return {
        "session_id": session_id,
        "metrics": {
            "turns_count": len(messages),
            "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0,
            "interruptions": interruptions,
        },
    }


@router.get("/{session_id}/recording")
async def get_recording(session_id: str):
    supabase = get_supabase()
    session_check = supabase.table("sessions").select("id").eq("id", session_id).execute()
    if not session_check.data:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "recording_url": None}
