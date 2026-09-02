from fastapi import APIRouter, HTTPException, status
from app.models.database import get_supabase
from app.models.schemas import SessionCreate, Session, MessageRequest
from app.services.llm import generate_response, get_persona_system_prompt
from app.services.session import create_session, save_turn, load_turns, end_session, resolve_persona_id
from app.services.call_summarizer import generate_call_summary
from typing import List

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", response_model=Session)
async def create_session_route(data: SessionCreate):
    user_id = data.user_id or str(__import__("uuid").uuid4())
    resolved_persona_id = await resolve_persona_id(data.persona_id)
    db_session_id = await create_session(
        persona_id=resolved_persona_id,
        user_id=user_id,
        status=data.status or "active",
        selected_voice=data.selected_voice,
    )
    supabase = get_supabase()
    res = supabase.table("sessions").select("*").eq("id", db_session_id).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to create session")
    return Session(**res.data[0])


@router.get("", response_model=List[Session])
async def list_sessions():
    supabase = get_supabase()
    res = supabase.table("sessions").select("*").order("started_at", desc=True).execute()
    return [Session(**s) for s in (res.data or [])]


@router.get("/{session_id}")
async def get_session_details(session_id: str):
    supabase = get_supabase()
    session_res = supabase.table("sessions").select("*").eq("id", session_id).execute()
    if not session_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    messages_res = supabase.table("messages").select("*").eq("session_id", session_id).order("sequence_number").execute()
    session = session_res.data[0]
    session["messages"] = messages_res.data or []
    return session


@router.get("/{session_id}/summary")
async def get_session_summary(session_id: str):
    supabase = get_supabase()
    session_res = supabase.table("sessions").select("*").eq("id", session_id).execute()
    if not session_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    session = session_res.data[0]
    summary = session.get("summary")
    if summary:
        return {"session_id": session_id, "summary": summary}

    messages_res = supabase.table("messages").select("speaker,text").eq("session_id", session_id).order("sequence_number").execute()
    history = [{"role": m["speaker"], "content": m["text"]} for m in (messages_res.data or [])]
    if not history:
        return {"session_id": session_id, "summary": ""}

    try:
        summary = await generate_call_summary(history)
    except Exception:
        summary = ""

    return {"session_id": session_id, "summary": summary or ""}


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    await end_session(session_id)
    supabase = get_supabase()
    supabase.table("messages").delete().eq("session_id", session_id).execute()
    supabase.table("sessions").delete().eq("id", session_id).execute()
    return {"status": "deleted"}


@router.post("/{session_id}/message")
async def send_message(session_id: str, data: MessageRequest):
    supabase = get_supabase()
    session_check = supabase.table("sessions").select("id,persona_id").eq("id", session_id).execute()
    if not session_check.data:
        raise HTTPException(status_code=404, detail="Session not found")

    persona_id = session_check.data[0].get("persona_id")
    system_prompt = await get_persona_system_prompt(persona_id) if persona_id else "You are a helpful voice assistant."

    user_text = data.text or ""
    await save_turn(session_id, "user", user_text)

    history = await load_turns(session_id)
    response_text = await generate_response(history, system_prompt)
    await save_turn(session_id, "assistant", response_text)

    return {"session_id": session_id, "text": response_text}
