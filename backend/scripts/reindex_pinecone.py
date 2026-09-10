import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings
from app.models.database import get_supabase
from app.services.rag import _get_pinecone_index, generate_embeddings

logger = logging.getLogger(__name__)


async def fetch_documents_with_chunks(supabase):
    docs_res = supabase.table("documents").select("id, persona_id, filename").execute()
    documents = docs_res.data or []
    logger.info("Loaded %d documents", len(documents))

    chunks_res = supabase.table("document_chunks").select("id, document_id, chunk_text, embedding_id, metadata").execute()
    chunks_by_doc = {}
    for chunk in chunks_res.data or []:
        doc_id = chunk.get("document_id")
        if doc_id is None:
            continue
        chunks_by_doc.setdefault(str(doc_id), []).append(chunk)
    logger.info("Loaded %d chunks across %d documents", sum(len(v) for v in chunks_by_doc.values()), len(chunks_by_doc))
    return documents, chunks_by_doc


async def reindex_pinecone(supabase, batch_size: int = 100):
    documents, chunks_by_doc = await fetch_documents_with_chunks(supabase)
    if not documents:
        logger.info("Nothing to re-index")
        return

    index = _get_pinecone_index()

    total_upserted = 0
    for doc in documents:
        doc_id = str(doc["id"])
        persona_id = doc.get("persona_id")
        filename = doc.get("filename") or ""
        chunks = chunks_by_doc.get(doc_id, [])
        if not chunks:
            logger.info("Skipping document %s: no chunks", doc_id)
            continue

        texts = [c.get("chunk_text") or "" for c in chunks]
        texts = [t.strip() for t in texts if t.strip()]
        if not texts:
            logger.info("Skipping document %s: no chunk text", doc_id)
            continue

        embeddings = generate_embeddings(texts)

        vectors = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            metadata = {
                "document_id": doc_id,
                "chunk_index": i,
                "text": chunk.get("chunk_text") or "",
                "filename": filename,
                "persona_id": str(persona_id) if persona_id else "",
            }
            vectors.append({
                "id": str(chunk.get("embedding_id") or f"{doc_id}_{i}"),
                "values": embedding,
                "metadata": metadata,
            })

        for i in range(0, len(vectors), batch_size):
            batch = vectors[i:i + batch_size]
            index.upsert(vectors=batch)
            total_upserted += len(batch)

        logger.info("Re-indexed document %s (%s chunks)", doc_id, len(vectors))

    logger.info("Re-index complete. Total vectors upserted: %d", total_upserted)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger.info("Re-index started at %s", datetime.now(timezone.utc).isoformat())

    if not settings.supabase_url or not settings.supabase_service_role_key or not settings.pinecone_api_key:
        logger.error("Missing required settings: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, PINECONE_API_KEY")
        return

    supabase = get_supabase()
    asyncio.run(reindex_pinecone(supabase))
    logger.info("Re-index finished at %s", datetime.now(timezone.utc).isoformat())


if __name__ == "__main__":
    main()
