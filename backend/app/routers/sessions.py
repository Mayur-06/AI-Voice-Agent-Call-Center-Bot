import asyncio
from fastapi import APIRouter, HTTPException, status
from app.models.database import get_supabase, run_supabase
from app.models.schemas import SessionCreate, Session, MessageRequest, SessionDocumentAttach
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
    res = await run_supabase(lambda: supabase.table("sessions").select("*").eq("id", db_session_id).execute())
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to create session")
    return Session(**res.data[0])


@router.post("/{session_id}/documents")
async def attach_session_documents(session_id: str, data: SessionDocumentAttach):
    """Attach already-uploaded documents to this call's retrieval scope."""
    supabase = get_supabase()
    session_res = await run_supabase(
        lambda: supabase.table("sessions").select("id,persona_id").eq("id", session_id).limit(1).execute()
    )
    if not session_res.data:
        raise HTTPException(status_code=404, detail="Session not found")
    session = session_res.data[0]
    document_ids = list(dict.fromkeys(str(document_id) for document_id in data.document_ids))
    documents_res = await run_supabase(
        lambda: supabase.table("documents").select("id,persona_id,status")
        .in_("id", document_ids).eq("persona_id", session["persona_id"]).execute()
    )
    documents = documents_res.data or []
    found_ids = {str(document["id"]) for document in documents}
    if len(found_ids) != len(document_ids):
        raise HTTPException(status_code=400, detail="Documents must belong to this session's persona")
    not_indexed = [str(document["id"]) for document in documents if document.get("status") != "indexed"]
    if not_indexed:
        raise HTTPException(status_code=409, detail="Documents are still being indexed")

    await run_supabase(
        lambda: supabase.table("session_documents").upsert(
            [{"session_id": session_id, "document_id": document_id} for document_id in document_ids],
            on_conflict="session_id,document_id",
        ).execute()
    )
    return {"session_id": session_id, "document_ids": document_ids}


@router.get("", response_model=List[Session])
async def list_sessions():
    supabase = get_supabase()
    sessions_res = await run_supabase(lambda: supabase.table("sessions").select("*").order("started_at", desc=True).execute())
    sessions = sessions_res.data or []

    persona_ids = [str(s.get("persona_id")) for s in sessions if s.get("persona_id")]
    persona_map = {}
    if persona_ids:
        personas_res = await run_supabase(lambda: supabase.table("personas").select("id, name").in_("id", persona_ids).execute())
        for p in (personas_res.data or []):
            persona_map[str(p["id"])] = p.get("name", "Unknown")

    voice_ids = [s.get("selected_voice") for s in sessions if s.get("selected_voice")]
    voice_map = {}
    if voice_ids:
        voices_res = await run_supabase(lambda: supabase.table("voices").select("voice_id, name").in_("voice_id", voice_ids).execute())
        for v in (voices_res.data or []):
            voice_id = v.get("voice_id")
            if not voice_id:
                continue
            voice_map[str(voice_id)] = v.get("name", "Unknown")

    result = []
    for s in sessions:
        row = dict(s)
        row["persona_name"] = persona_map.get(str(s.get("persona_id", "")), "Unknown")
        row["selected_voice_name"] = voice_map.get(str(s.get("selected_voice", "")), "Unknown")
        result.append(row)
    return result


@router.get("/{session_id}")
async def get_session_details(session_id: str):
    supabase = get_supabase()
    session_res = await run_supabase(lambda: supabase.table("sessions").select("*").eq("id", session_id).execute())
    if not session_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    session = session_res.data[0]
    persona_id = session.get("persona_id")
    selected_voice = session.get("selected_voice")

    persona_name = None
    if persona_id:
        persona_res = await run_supabase(lambda: supabase.table("personas").select("name, domain").eq("id", persona_id).limit(1).execute())
        if persona_res.data:
            persona_name = persona_res.data[0].get("name")
            session["persona_domain"] = persona_res.data[0].get("domain")

    selected_voice_name = None
    if selected_voice:
        voice_res = await run_supabase(lambda: supabase.table("voices").select("name").eq("voice_id", selected_voice).limit(1).execute())
        if voice_res.data:
            selected_voice_name = voice_res.data[0].get("name")

    session["persona_name"] = persona_name
    session["selected_voice_name"] = selected_voice_name

    messages_res = await run_supabase(lambda: supabase.table("messages").select("*").eq("session_id", session_id).order("sequence_number").execute())
    session["messages"] = messages_res.data or []
    return session


@router.get("/{session_id}/summary")
async def get_session_summary(session_id: str):
    supabase = get_supabase()
    session_res = await run_supabase(lambda: supabase.table("sessions").select("*").eq("id", session_id).execute())
    if not session_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    session = session_res.data[0]
    summary = session.get("summary")
    if summary:
        return {"session_id": session_id, "summary": summary}

    messages_res = await run_supabase(lambda: supabase.table("messages").select("speaker,text").eq("session_id", session_id).order("sequence_number").execute())
    history = [{"role": m["speaker"], "content": m["text"]} for m in (messages_res.data or [])]
    if not history:
        return {"session_id": session_id, "summary": ""}

    try:
        summary = await asyncio.wait_for(generate_call_summary(history), timeout=30)
    except asyncio.TimeoutError:
        summary = ""
    except Exception:
        summary = ""

    return {"session_id": session_id, "summary": summary or ""}


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    await end_session(session_id)
    supabase = get_supabase()
    await run_supabase(lambda: supabase.table("messages").delete().eq("session_id", session_id).execute())
    await run_supabase(lambda: supabase.table("sessions").delete().eq("id", session_id).execute())
    return {"status": "deleted"}


@router.post("/{session_id}/message")
async def send_message(session_id: str, data: MessageRequest):
    supabase = get_supabase()
    session_check = await run_supabase(lambda: supabase.table("sessions").select("id,persona_id").eq("id", session_id).execute())
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
