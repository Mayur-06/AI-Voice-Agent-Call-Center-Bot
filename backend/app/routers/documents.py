from fastapi import APIRouter, Depends, File, UploadFile, Query, HTTPException
from app.models.database import get_supabase, get_storage_admin
from app.services.rag import split_text, generate_embeddings, index_document
from app.services.storage import upload_document, ensure_documents_bucket
from app.config import settings
from PyPDF2 import PdfReader
import uuid
from datetime import datetime, timezone
from typing import List

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("/")
async def list_documents():
    supabase = get_supabase()
    res = supabase.table("documents").select("*").order("uploaded_at", desc=True).execute()
    return res.data or []


@router.post("/upload")
async def upload_document(
    files: List[UploadFile] = File(...),
    session_id: str = Query(None),
):
    ensure_documents_bucket()
    uploaded = []

    for file in files:
        content_bytes = await file.read()

        if not content_bytes:
            raise HTTPException(status_code=400, detail=f"Empty file: {file.filename}")

        file_type = file.content_type or "application/octet-stream"
        filename = file.filename or "uploaded"

        if filename.lower().endswith(".pdf"):
            try:
                import io
                reader = PdfReader(io.BytesIO(content_bytes))
                text = "\n".join(page.extract_text() or "" for page in reader.pages)
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Failed to extract text from PDF {filename}: {exc}")
        else:
            try:
                text = content_bytes.decode("utf-8")
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Failed to decode file {filename}: {exc}")

        if not text.strip():
            raise HTTPException(status_code=400, detail=f"Empty file: {filename}")

        chunks = split_text(text)
        if not chunks:
            raise HTTPException(status_code=400, detail=f"No text could be extracted from document {filename}")

        doc_id = str(uuid.uuid4())
        storage_path = upload_document(content_bytes, filename, file_type)

        supabase = get_supabase()
        insert_res = supabase.table("documents").insert({
            "id": doc_id,
            "session_id": session_id,
            "filename": filename,
            "file_type": file_type,
            "storage_path": storage_path,
            "status": "uploaded",
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }).execute()

        await index_document(doc_id, chunks, session_id, filename=filename)

        inserted = insert_res.data[0] if isinstance(insert_res.data, list) and insert_res.data else {}
        uploaded.append({
            "id": inserted.get("id", doc_id),
            "filename": inserted.get("filename", filename),
            "file_type": inserted.get("file_type", file_type),
            "storage_path": inserted.get("storage_path", storage_path),
            "chunks_count": len(chunks),
            "status": "indexed",
            "uploaded_at": inserted.get("uploaded_at", datetime.now(timezone.utc).isoformat()),
        })

    return {"documents": uploaded}
