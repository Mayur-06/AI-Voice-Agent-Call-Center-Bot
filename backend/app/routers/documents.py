import io
import re
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from PyPDF2 import PdfReader
from app.models.database import get_supabase, get_storage_admin
from app.models.schemas import Document
from app.services.rag import split_text, index_document_chunks
from app.config import settings
from app.routers.auth import get_current_user

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _sanitize_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[^\x09\x0A\x0D\x20-\x7E\u0080-\u00FF]", "", text)
    return text.strip()


@router.post("/upload", response_model=Document)
async def upload_document(persona_id: str, file: UploadFile = File(...), user=Depends(get_current_user)):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    supabase = get_supabase()
    storage = get_storage_admin()

    doc_res = supabase.table("documents").insert({
        "persona_id": persona_id,
        "filename": file.filename,
        "chunks_count": 0,
    }).execute()
    if not doc_res.data:
        raise HTTPException(status_code=500, detail="Failed to create document record")
    document = doc_res.data[0]
    document_id = document["id"]

    storage_path = f"{document_id}/{file.filename}"
    try:
        storage.from_("documents").upload(storage_path, content, {"content-type": file.content_type or "application/pdf"})
    except Exception:
        pass

    try:
        pdf_file = io.BytesIO(content)
        reader = PdfReader(pdf_file)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to extract text from PDF: {str(e)}")

    text = _sanitize_text(text)
    chunks = split_text(text)
    chunks_count = len(chunks)

    if chunks_count > 0:
        chunk_rows = [
            {
                "document_id": document_id,
                "chunk_text": chunk,
                "embedding_id": None,
            }
            for chunk in chunks
        ]
        supabase.table("document_chunks").insert(chunk_rows).execute()
        await index_document_chunks(document_id, chunks)

    supabase.table("documents").update({"chunks_count": chunks_count}).eq("id", document_id).execute()

    return Document(**{**document, "chunks_count": chunks_count})