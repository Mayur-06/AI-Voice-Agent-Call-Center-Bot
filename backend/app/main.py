import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import personas, sessions, documents, voices, analytics
from app.routers import transcripts, recordings, sentiment as sentiment_router, metrics, exports
from app.websocket.handler import router as ws_router
from app.services.rag import check_pinecone_health
from app.services.storage import ensure_recordings_bucket, ensure_documents_bucket

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Startup: supabase_url=%s anon_key=%s service_key=%s cwd=%s", bool(settings.supabase_url), bool(settings.supabase_anon_key), bool(settings.supabase_service_role_key), __import__("os").getcwd())
    check_pinecone_health()
    ensure_documents_bucket()
    ensure_recordings_bucket()
    yield


app = FastAPI(title="AI Voice Agent Backend", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


app.include_router(personas.router)
app.include_router(sessions.router)
app.include_router(documents.router)
app.include_router(voices.router)
app.include_router(analytics.router)
app.include_router(ws_router)
app.include_router(transcripts.router)
app.include_router(recordings.router)
app.include_router(sentiment_router.router)
app.include_router(metrics.router)
app.include_router(exports.router)
