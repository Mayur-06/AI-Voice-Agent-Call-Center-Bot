import logging
import os
import re
import httpx
import chromadb
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer
from app.config import settings

logger = logging.getLogger(__name__)

_chunk_size = 500
_chunk_overlap = 50
_collection_name = "default"
_client = None
_collection = None
_chromadb_available = False
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


def _get_client():
    global _client, _collection, _chromadb_available
    if _client is None:
        try:
            _client = chromadb.HttpClient(host="localhost", port=8001)
            _client.heartbeat()
            _chromadb_available = True
        except Exception:
            _client = chromadb.Client(ChromaSettings(anonymized_telemetry=False))
            _chromadb_available = False
    if _collection is None:
        _collection = _client.get_or_create_collection(_collection_name)
    return _client, _collection


def check_chromadb_health():
    global _chromadb_available
    try:
        client = chromadb.HttpClient(host="localhost", port=8001)
        client.heartbeat()
        _chromadb_available = True
        logger.info("ChromaDB server is reachable at %s", settings.chromadb_url)
    except Exception:
        _chromadb_available = False
        logger.warning(
            "ChromaDB server is not reachable at %s. Falling back to in-memory client. "
            "Document retrieval and indexing will not persist across restarts.",
            settings.chromadb_url,
        )


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


async def retrieve_context(query: str, top_k: int = 3) -> list[str]:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.chromadb_url}/api/collections/{_collection_name}/query",
                json={"query_texts": [query], "n_results": top_k},
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            return [doc[0] for doc in data.get("ids", [[]])]
    except Exception:
        try:
            _, collection = _get_client()
            results = collection.query(query_texts=[query], n_results=top_k)
            ids = results.get("ids", [[]])
            if ids:
                return ids[0]
        except Exception:
            pass
        return []


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    model = _get_model()
    embeddings = model.encode(texts, show_progress_bar=False)
    return embeddings.tolist()


async def index_document_chunks(document_id: str, chunks: list[str]):
    if not chunks:
        return
    embeddings = generate_embeddings(chunks)
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{settings.chromadb_url}/api/collections/{_collection_name}/add",
                json={
                    "ids": [f"{document_id}_{i}" for i in range(len(chunks))],
                    "documents": chunks,
                    "embeddings": embeddings,
                    "metadatas": [{"document_id": document_id, "chunk_index": i} for i in range(len(chunks))],
                },
                timeout=30.0,
            )
    except Exception:
        try:
            _, collection = _get_client()
            collection.add(
                ids=[f"{document_id}_{i}" for i in range(len(chunks))],
                documents=chunks,
                embeddings=embeddings,
                metadatas=[{"document_id": document_id, "chunk_index": i} for i in range(len(chunks))],
            )
        except Exception:
            pass