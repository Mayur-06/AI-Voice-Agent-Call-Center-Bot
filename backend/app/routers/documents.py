from fastapi import APIRouter, Depends, File, UploadFile, Query
from app.models.database import get_supabase, get_storage_admin
from app.services.rag import split_text, generate_embeddings
from app.services.rag import index_document_chunks
from app.config import settings
from PyPDF2 import PdfReader
import uuid
from datetime import datetime, timezone

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("/")
async def list_documents():
    supabase = get_supabase()
    res = supabase.table("documents").select("*").order("created_at", desc=True).execute()
    return res.data or []


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    persona_id: str = Query("default"),
):
    content_bytes = await file.read()

    if not content_bytes:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Empty file")

    if file.filename and file.filename.lower().endswith(".pdf"):
        try:
            import io
            reader = PdfReader(io.BytesIO(content_bytes))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail=f"Failed to extract text from PDF: {exc}")
    else:
        try:
            text = content_bytes.decode("utf-8")
        except Exception as exc:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail=f"Failed to decode file: {exc}")

    if not text.strip():
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Empty file")

    chunks = split_text(text)
    embeddings = generate_embeddings(chunks)
    doc_id = str(uuid.uuid4())

    supabase = get_supabase()
    insert_res = supabase.table("documents").insert({
        "id": doc_id,
        "persona_id": persona_id,
        "filename": file.filename or "uploaded",
        "chunks_count": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }).execute()

    await index_document_chunks(doc_id, chunks)

    inserted = insert_res.data[0] if isinstance(insert_res.data, list) and insert_res.data else {}
    return {
        "id": inserted.get("id", doc_id),
        "persona_id": inserted.get("persona_id", persona_id),
        "filename": inserted.get("filename", file.filename or "uploaded"),
        "chunks_count": len(chunks),
        "created_at": inserted.get("created_at", datetime.now(timezone.utc).isoformat()),
    }
