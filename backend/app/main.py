import logging
import os
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import personas, sessions, documents, voices, analytics
from app.routers import transcripts, recordings, sentiment as sentiment_router, metrics, exports
from app.websocket.handler import router as ws_router
from app.services.rag import check_pinecone_health
from app.services.storage import ensure_recordings_bucket, ensure_documents_bucket

# Ensure log directory exists
log_dir = os.path.join(os.path.dirname(__file__), "..", "log")
os.makedirs(log_dir, exist_ok=True)

# Configure logging to both console and file
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(log_dir, "backend.log"), mode="a"),
    ],
)
logger = logging.getLogger(__name__)

# Ensure VAD logger propagates
logging.getLogger("app.services.vad").setLevel(logging.INFO)
logging.getLogger("app.orchestration.stages").setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Startup: supabase_url=%s anon_key=%s service_key=%s cwd=%s", bool(settings.supabase_url), bool(settings.supabase_anon_key), bool(settings.supabase_service_role_key), __import__("os").getcwd())
    check_pinecone_health()
    ensure_documents_bucket()
    ensure_recordings_bucket()
    app.state.audio_executor = ThreadPoolExecutor(
        max_workers=settings.ws_audio_executor_workers,
        thread_name_prefix="audio",
    )
    app.state.vad_executor = ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix="vad",
    )
    app.state.embedding_executor = ProcessPoolExecutor(
        max_workers=settings.ws_embedding_executor_workers,
    )
    try:
        yield
    finally:
        app.state.audio_executor.shutdown(wait=True)
        app.state.vad_executor.shutdown(wait=True)
        app.state.embedding_executor.shutdown(wait=True)


app = FastAPI(title="AI Voice Agent Backend", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_origin_regex=r"https://.*\.vercel\.app$",
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
