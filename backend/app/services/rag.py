import logging
import os
import re
import uuid
from typing import Optional

from pinecone import Pinecone
from sentence_transformers import SentenceTransformer
from app.config import settings
from app.models.database import get_supabase

logger = logging.getLogger(__name__)

_chunk_size = 500
_chunk_overlap = 50
_pinecone_index = None
_model = None


if settings.hf_hub_disable_symlinks_warning:
    os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

if settings.hf_token:
    os.environ["HF_TOKEN"] = settings.hf_token


def _get_model():
    global _model
    if _model is None:
        try:
            _model = SentenceTransformer("all-MiniLM-L6-v2", device=settings.embedding_device)
        except Exception:
            _model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
    return _model


def _get_pinecone_index():
    global _pinecone_index
    if _pinecone_index is None:
        pc = Pinecone(api_key=settings.pinecone_api_key)
        _pinecone_index = pc.Index(settings.pinecone_index_name)
    return _pinecone_index


def check_pinecone_health():
    try:
        index = _get_pinecone_index()
        index.describe_index_stats()
        logger.info("Pinecone index %s is reachable", settings.pinecone_index_name)
    except Exception as exc:
        logger.warning("Pinecone is not reachable: %s", exc)


def split_text(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= _chunk_size:
        return [cleaned]
    chunks = []
    start = 0
    while start < len(cleaned):
        end = start + _chunk_size
        chunk = cleaned[start:end]
        chunks.append(chunk)
        start = end - _chunk_overlap
    return [chunk for chunk in chunks if chunk.strip()]


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    model = _get_model()
    embeddings = model.encode(texts, show_progress_bar=False)
    return embeddings.tolist()


async def _upsert_pinecone(vectors: list[dict], batch_size: int = 100):
    import asyncio
    loop = asyncio.get_running_loop()
    index = _get_pinecone_index()

    def _upsert_batch(batch):
        index.upsert(vectors=batch)

    for i in range(0, len(vectors), batch_size):
        batch = vectors[i:i + batch_size]
        await loop.run_in_executor(None, _upsert_batch, batch)


async def store_chunks_in_pinecone(document_id: str, session_id: Optional[str], chunks: list[str], embeddings: list[list[float]], filename: str = ""):
    if not chunks:
        return
    vectors = []
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        vectors.append({
            "id": f"{document_id}_{i}",
            "values": embedding,
            "metadata": {
                "document_id": str(document_id),
                "chunk_index": i,
                "text": chunk,
                "filename": filename,
                **({"session_id": str(session_id)} if session_id else {}),
            },
        })

    await _upsert_pinecone(vectors)


async def _query_pinecone(query_embedding: list[float], top_k: int, filter_dict: Optional[dict]) -> list[tuple[str, str]]:
    import asyncio
    loop = asyncio.get_running_loop()
    index = _get_pinecone_index()

    def _do_query():
        return index.query(
            vector=query_embedding,
            top_k=top_k,
            filter=filter_dict,
            include_metadata=True,
        )

    results = await loop.run_in_executor(None, _do_query)
    chunks = []
    for match in results.matches:
        text = match.metadata.get("text", "")
        filename = match.metadata.get("filename", "")
        if text:
            chunks.append((filename, text))
    return chunks


async def retrieve_relevant_chunks(query: str, top_k: int = 3, session_id: Optional[str] = None, document_id: Optional[str] = None) -> list[tuple[str, str]]:
    import asyncio
    loop = asyncio.get_running_loop()
    query_embedding = await loop.run_in_executor(None, _encode_query, query)

    filter_dict = {}
    if document_id:
        filter_dict["document_id"] = {"$eq": str(document_id)}
    elif session_id:
        filter_dict["session_id"] = {"$eq": str(session_id)}

    chunks = await _query_pinecone(query_embedding, top_k, filter_dict if filter_dict else None)
    if not chunks and session_id:
        logger.info("RAG fallback: no chunks for session %s, retrying without filter", session_id)
        chunks = await _query_pinecone(query_embedding, top_k, None)
        logger.info("RAG fallback result for session %s: %s chunks", session_id, len(chunks))
    return chunks


async def index_document(document_id: str, chunks: list[str], session_id: Optional[str] = None, filename: str = ""):
    if not chunks:
        return
    import asyncio
    loop = asyncio.get_running_loop()
    embeddings = await loop.run_in_executor(None, generate_embeddings, chunks)

    supabase = get_supabase()
    metadata_list = []
    for i, chunk in enumerate(chunks):
        chunk_id = str(uuid.uuid4())
        metadata_list.append({
            "id": chunk_id,
            "document_id": str(document_id),
            "chunk_text": chunk,
            "embedding_id": f"{document_id}_{i}",
            "metadata": {"chunk_index": i, "session_id": str(session_id) if session_id else None, "filename": filename},
        })

    if metadata_list:
        await loop.run_in_executor(None, lambda: supabase.table("document_chunks").insert(metadata_list).execute())

    await store_chunks_in_pinecone(document_id, session_id, chunks, embeddings, filename)

    try:
        await loop.run_in_executor(
            None,
            lambda: supabase.table("documents").update({"status": "indexed"}).eq("id", str(document_id)).execute()
        )
    except Exception:
        pass


def _encode_query(query: str) -> list[float]:
    model = _get_model()
    return model.encode([query], show_progress_bar=False).tolist()[0]


def requires_rag(query: str) -> bool:
    question_words = {
        "what", "how", "why", "when", "where", "who", "which",
        "explain", "describe", "tell", "summarize", "find", "search",
        "look up", "look for", "according to",
    }
    document_indicators = {
        "document", "policy", "contract", "agreement", "report",
        "file", "upload", "according to", "in the", "from the",
        "states that", "says that", "mentioned in", "refer to",
    }
    casual_phrases = {
        "hello", "hi there", "how are you", "good morning",
        "good afternoon", "good evening", "nice to meet",
        "i can", "i could", "i would", "i should", "i will",
        "that's great", "thank you", "thanks", "okay", "ok",
        "yes", "no", "maybe", "i think", "i guess",
    }

    q_lower = query.lower().strip()
    if any(q_lower.startswith(w) or f" {w} " in f" {q_lower} " for w in question_words):
        return True
    if any(indicator in q_lower for indicator in document_indicators):
        return True
    if any(q_lower.startswith(p) or f" {p} " in f" {q_lower} " for p in casual_phrases):
        return False
    return len(q_lower.split()) > 3
