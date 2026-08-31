import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import personas, sessions, documents, voices, analytics
from app.websocket.handler import router as ws_router
from app.services.rag import check_chromadb_health
from app.services.storage import ensure_recordings_bucket

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    check_chromadb_health()
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
