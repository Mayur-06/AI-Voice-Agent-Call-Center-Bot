import asyncio
import logging
import logging.handlers
import os
import queue
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import personas, sessions, documents, voices, analytics
from app.routers.personas import _ensure_personas
from app.routers.voices import _ensure_voices
from app.routers import transcripts, recordings, sentiment as sentiment_router, metrics, exports
from app.websocket.handler import router as ws_router
from app.services.rag import check_pinecone_health, warm_up as warm_up_embeddings
from app.services.stt import close_client as close_stt_client
from app.services.storage import ensure_recordings_bucket, ensure_documents_bucket

# Ensure log directory exists
# Same tree the per-session call logs use; "../log" was a second, stray one.
log_dir = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(log_dir, exist_ok=True)

# Logging is routed through a queue so that writing to disk never blocks the
# event loop. A synchronous FileHandler called from async code adds latency
# jitter to the audio path on every log line.
_log_queue: queue.Queue = queue.Queue(-1)
_formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
_stream_handler = logging.StreamHandler()
_stream_handler.setFormatter(_formatter)
_file_handler = logging.FileHandler(os.path.join(log_dir, "backend.log"), mode="a")
_file_handler.setFormatter(_formatter)
_log_listener = logging.handlers.QueueListener(
    _log_queue, _stream_handler, _file_handler, respect_handler_level=True
)

logging.basicConfig(level=logging.INFO, handlers=[logging.handlers.QueueHandler(_log_queue)])
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _log_listener.start()
    logger.info(
        "Startup: supabase_url=%s anon_key=%s service_key=%s cwd=%s",
        bool(settings.supabase_url), bool(settings.supabase_anon_key),
        bool(settings.supabase_service_role_key), os.getcwd(),
    )
    check_pinecone_health()
    ensure_documents_bucket()
    ensure_recordings_bucket()
    # Seed reference data here rather than lazily inside GET /api/personas and
    # GET /api/voices. The UI never calls those endpoints - it ships its own
    # persona list and resolves by name - so against a fresh database the very
    # first "start call" failed with "No personas available".
    for seed, label in ((_ensure_personas, "personas"), (_ensure_voices, "voices")):
        try:
            await seed()
        except Exception:
            logger.exception("Failed to seed %s", label)
    app.state.audio_executor = ThreadPoolExecutor(
        max_workers=settings.ws_audio_executor_workers,
        thread_name_prefix="audio",
    )
    app.state.vad_executor = ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix="vad",
    )
    # RAG owns its own pool (app.services.rag). The ProcessPoolExecutor that
    # used to live here forked the whole application and was never used.
    app.state.embedding_executor = None

    # Warm the embedding model off the critical path of the first call.
    asyncio.get_running_loop().run_in_executor(None, warm_up_embeddings)
    try:
        yield
    finally:
        await close_stt_client()
        app.state.audio_executor.shutdown(wait=True)
        app.state.vad_executor.shutdown(wait=True)
        _log_listener.stop()


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
