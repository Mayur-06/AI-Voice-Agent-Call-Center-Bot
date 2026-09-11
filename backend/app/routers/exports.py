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

from app.models.database import get_supabase, get_supabase_admin, run_supabase
from app.services.call_summarizer import generate_call_summary
from typing import List

router = APIRouter(prefix="/api/sessions", tags=["exports"])


def _validate_transcript_format(fmt: str) -> None:
    if fmt not in ("txt", "json"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="format must be txt or json")


def _validate_recording_format(fmt: str) -> None:
    if fmt not in ("mp3", "wav"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="format must be mp3 or wav")


_SUMMARY_LABELS = [
    ("key_topics", "Key topics"),
    ("decisions_made", "Decisions made"),
    ("action_items", "Action items"),
    ("dialogue_flow", "Dialogue flow"),
    ("resolution_status", "Resolution status"),
    ("sentiment_overview", "Sentiment overview"),
]


def _summary_sections(summary: str) -> list[tuple[str, str]]:
    """Render the stored summary as headed prose.

    The summary is persisted as a JSON blob. Writing it into the PDF verbatim
    handed the reader a wall of raw JSON, which is not a deliverable.
    """
    try:
        parsed = json.loads(summary or "")
    except (ValueError, TypeError):
        return [("Summary", summary or "No summary available.")]
    if not isinstance(parsed, dict):
        return [("Summary", str(parsed))]

    sections = []
    for key, label in _SUMMARY_LABELS:
        value = parsed.get(key)
        if not value:
            continue
        if isinstance(value, list):
            body = "\n".join(f"- {item}" for item in value)
        else:
            body = str(value)
        sections.append((label, body))
    return sections or [("Summary", "No summary available.")]


def _validate_summary_format(fmt: str) -> None:
    if fmt not in ("txt", "json", "pdf"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="format must be txt, json, or pdf")


@router.get("/{session_id}/export/transcript")
async def export_transcript(session_id: str, format: str = "json"):
    _validate_transcript_format(format)
    supabase = get_supabase()
    session_res = await run_supabase(lambda: supabase.table("sessions").select("id").eq("id", session_id).execute())
    if not session_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    res = await run_supabase(lambda: supabase.table("messages").select("*").eq("session_id", session_id).order("sequence_number").execute())
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
    session_res = await run_supabase(lambda: supabase.table("sessions").select("*").eq("id", session_id).execute())
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
    session_res = await run_supabase(lambda: supabase.table("sessions").select("*").eq("id", session_id).execute())
    if not session_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    session = session_res.data[0]
    summary = session.get("summary")
    if not summary:
        messages_res = await run_supabase(lambda: supabase.table("messages").select("speaker,text").eq("session_id", session_id).order("sequence_number").execute())
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
            from fpdf.enums import XPos, YPos
            # multi_cell(w=0) means "out to the right margin", so the cursor
            # must be returned to the left margin after each block or the next
            # call has zero width and fpdf raises.
            wrap = {"new_x": XPos.LMARGIN, "new_y": YPos.NEXT}
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 14)
            pdf.multi_cell(0, 10, f"Call Summary - Session {session_id}", **wrap)
            pdf.ln(2)
            for heading, body in _summary_sections(summary):
                pdf.set_font("Helvetica", "B", 12)
                pdf.multi_cell(0, 8, heading, **wrap)
                pdf.set_font("Helvetica", size=11)
                # Helvetica is latin-1 only in fpdf2; a stray unicode character
                # in a transcript would otherwise abort the whole export.
                pdf.multi_cell(0, 7, body.encode("latin-1", "replace").decode("latin-1"), **wrap)
                pdf.ln(2)
            # fpdf2 returns a bytearray, which Starlette's Response cannot
            # render - it produced a 500 on every PDF export.
            pdf_bytes = bytes(pdf.output())
            return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={session_id}_summary.pdf"})
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"PDF generation failed: {exc}") from exc

    content = summary or ""
    return Response(content=content, media_type="text/plain", headers={"Content-Disposition": f"attachment; filename={session_id}_summary.txt"})
