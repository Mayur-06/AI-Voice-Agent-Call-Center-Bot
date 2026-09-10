import asyncio
import io
import json
import os
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response, JSONResponse, FileResponse

try:
    from pydub import AudioSegment
except ImportError:  # pragma: no cover - optional dependency for MP3 export
    AudioSegment = None

from app.models.database import get_supabase, get_supabase_admin
from app.services.call_summarizer import generate_call_summary
from typing import List

router = APIRouter(prefix="/api/sessions", tags=["exports"])


def _validate_transcript_format(fmt: str) -> None:
    if fmt not in ("txt", "json"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="format must be txt or json")


def _validate_recording_format(fmt: str) -> None:
    if fmt not in ("mp3", "wav"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="format must be mp3 or wav")


def _validate_summary_format(fmt: str) -> None:
    if fmt not in ("txt", "json", "pdf"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="format must be txt, json, or pdf")


@router.get("/{session_id}/export/transcript")
async def export_transcript(session_id: str, format: str = "json"):
    _validate_transcript_format(format)
    supabase = get_supabase()
    session_res = supabase.table("sessions").select("id").eq("id", session_id).execute()
    if not session_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    res = supabase.table("messages").select("*").eq("session_id", session_id).order("sequence_number").execute()
    messages = res.data or []

    if format == "txt":
        lines = []
        for m in messages:
            ts = m.get("timestamp", "")
            lines.append(f"[{ts}] {m.get('speaker', '')}: {m.get('text', '')}")
        content = "\n".join(lines)
        return Response(content=content, media_type="text/plain", headers={"Content-Disposition": f"attachment; filename={session_id}_transcript.txt"})

    content = json.dumps(messages, indent=2)
    return Response(content=content, media_type="application/json", headers={"Content-Disposition": f"attachment; filename={session_id}_transcript.json"})


@router.get("/{session_id}/export/recording")
async def export_recording(session_id: str, format: str = "wav"):
    _validate_recording_format(format)
    supabase = get_supabase()
    session_res = supabase.table("sessions").select("*").eq("id", session_id).execute()
    if not session_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    session = session_res.data[0]
    recording_path = session.get("recording_url")
    wav_bytes = None
    if recording_path:
        try:
            storage = get_supabase_admin().storage.from_("recordings")
            file_data = storage.download(recording_path)
            wav_bytes = file_data
        except Exception:
            pass

    if wav_bytes is None:
        local_path = os.path.join("recordings", f"{session_id}.wav")
        if os.path.exists(local_path):
            with open(local_path, "rb") as fh:
                wav_bytes = fh.read()

    if wav_bytes is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")

    if format == "mp3":
        if AudioSegment is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="MP3 export requires pydub to be installed in the backend environment.",
            )

        audio = AudioSegment.from_file(io.BytesIO(wav_bytes), format="wav")
        mp3_buffer = io.BytesIO()
        audio.export(mp3_buffer, format="mp3", bitrate="128k")
        mp3_bytes = mp3_buffer.getvalue()
        return Response(content=mp3_bytes, media_type="audio/mpeg", headers={"Content-Disposition": f"attachment; filename={session_id}_recording.mp3"})

    return Response(content=wav_bytes, media_type="audio/wav", headers={"Content-Disposition": f"attachment; filename={session_id}_recording.wav"})


@router.get("/{session_id}/export/summary")
async def export_summary(session_id: str, format: str = "pdf"):
    _validate_summary_format(format)
    supabase = get_supabase()
    session_res = supabase.table("sessions").select("*").eq("id", session_id).execute()
    if not session_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    session = session_res.data[0]
    summary = session.get("summary")
    if not summary:
        messages_res = supabase.table("messages").select("speaker,text").eq("session_id", session_id).order("sequence_number").execute()
        history = [{"role": m["speaker"], "content": m["text"]} for m in (messages_res.data or [])]
        if history:
            try:
                summary = await asyncio.wait_for(generate_call_summary(history), timeout=30)
            except asyncio.TimeoutError:
                summary = ""
            except Exception:
                summary = ""
        else:
            summary = ""

    if format == "json":
        return JSONResponse(content={"session_id": session_id, "summary": summary or ""})

    if format == "pdf":
        try:
            from fpdf import FPDF
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Helvetica", size=12)
            pdf.cell(0, 10, f"Call Summary - Session {session_id}", ln=True)
            pdf.ln(2)
            pdf.multi_cell(0, 8, summary or "")
            pdf_bytes = pdf.output()
            return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={session_id}_summary.pdf"})
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"PDF generation failed: {exc}") from exc

    content = summary or ""
    return Response(content=content, media_type="text/plain", headers={"Content-Disposition": f"attachment; filename={session_id}_summary.txt"})
