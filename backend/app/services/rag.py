import asyncio
import logging
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from pinecone import Pinecone
from fastembed import TextEmbedding
from app.config import settings
from app.models.database import get_supabase

logger = logging.getLogger(__name__)

_chunk_size = 500
_chunk_overlap = 50
_pinecone_index = None
_model = None

# Dedicated pool. These calls previously ran on the default executor, which is
# also what asyncio.to_thread (and therefore every Supabase query) uses, so
# embedding, Pinecone and the database all contended for the same few threads.
_rag_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="rag")


def _run(fn, *args):
    return asyncio.get_running_loop().run_in_executor(_rag_executor, fn, *args)


def warm_up() -> None:
    """Load the embedding model at startup.

    Left lazy, the first RAG-triggering turn of the first call paid the model
    load (and possibly a download) inside the user's critical path.
    """
    try:
        _get_model()
        logger.info("Embedding model warmed up")
    except Exception as exc:
        logger.warning("Embedding model warm-up failed: %s", exc)


if settings.hf_hub_disable_symlinks_warning:
    os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

if settings.hf_token:
    os.environ["HF_TOKEN"] = settings.hf_token


def _get_model():
    global _model
    if _model is None:
        # FastEmbed runs the ONNX export of the same MiniLM model on CPU.  It
        # avoids pulling PyTorch and its CUDA-related libraries into production.
        _model = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")
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
    return [embedding.tolist() for embedding in model.embed(texts)]


async def _upsert_pinecone(vectors: list[dict], batch_size: int = 100):
    import asyncio
    loop = asyncio.get_running_loop()
    index = _get_pinecone_index()

    def _upsert_batch(batch):
        index.upsert(vectors=batch)

    for i in range(0, len(vectors), batch_size):
        batch = vectors[i:i + batch_size]
        await loop.run_in_executor(None, _upsert_batch, batch)


async def store_chunks_in_pinecone(document_id: str, chunks: list[str], embeddings: list[list[float]], filename: str = "", persona_id: Optional[str] = None):
    if not chunks:
        return
    vectors = []
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        metadata = {
            "document_id": str(document_id),
            "chunk_index": i,
            "text": chunk,
            "filename": filename,
            "persona_id": str(persona_id) if persona_id else "",
        }
        vectors.append({
            "id": f"{document_id}_{i}",
            "values": embedding,
            "metadata": metadata,
        })

    await _upsert_pinecone(vectors)


async def _query_pinecone(query_embedding: list[float], top_k: int, filter_dict: Optional[dict]) -> list[tuple[str, str]]:
    index = _get_pinecone_index()

    def _do_query():
        return index.query(
            vector=query_embedding,
            top_k=top_k,
            filter=filter_dict,
            include_metadata=True,
        )

    results = await _run(_do_query)
    chunks = []
    for match in results.matches:
        text = match.metadata.get("text", "")
        filename = match.metadata.get("filename", "")
        if text:
            chunks.append((filename, text))
    return chunks


async def retrieve_relevant_chunks(query: str, persona_id: str, top_k: int = 3) -> list[tuple[str, str]]:
    query_embedding = await _run(_encode_query, query)

    filter_dict = {"persona_id": {"$eq": str(persona_id)}}
    chunks = await _query_pinecone(query_embedding, top_k, filter_dict)
    return chunks


async def index_document(document_id: str, chunks: list[str], filename: str = "", persona_id: Optional[str] = None):
    if not chunks:
        return
    import asyncio
    loop = asyncio.get_running_loop()
    chunks = [chunk.replace("\x00", "") for chunk in chunks]
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
            "metadata": {"chunk_index": i, "filename": filename, "persona_id": str(persona_id) if persona_id else None},
        })

    if metadata_list:
        await loop.run_in_executor(None, lambda: supabase.table("document_chunks").insert(metadata_list).execute())

    await store_chunks_in_pinecone(document_id, chunks, embeddings, filename, persona_id)

    try:
        await loop.run_in_executor(
            None,
            lambda: supabase.table("documents").update({"status": "indexed"}).eq("id", str(document_id)).execute()
        )
    except Exception:
        pass


def _encode_query(query: str) -> list[float]:
    model = _get_model()
    return next(model.embed([query])).tolist()


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
    # Small talk short-circuits first: it must not trigger retrieval.
    if any(q_lower.startswith(p) for p in casual_phrases):
        return False
    # An explicit reference to source material always retrieves.
    if any(indicator in q_lower for indicator in document_indicators):
        return True
    # A question only retrieves if it is substantive enough to be about
    # something in the knowledge base.
    if any(q_lower.startswith(w) or f" {w} " in f" {q_lower} " for w in question_words):
        return len(q_lower.split()) > 4
    return False
