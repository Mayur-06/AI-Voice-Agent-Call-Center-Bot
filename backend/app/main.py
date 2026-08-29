import logging
import asyncio
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import auth, personas, sessions, documents, voices, analytics, test
from app.websocket.handler import router as ws_router
from app.services.rag import check_chromadb_health

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    check_chromadb_health()
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


@app.get("/test/logs")
async def stream_logs(session: str = "global"):
    async def event_generator():
        from app.websocket.handler import _stream_session_logs
        async for line in _stream_session_logs(session):
            yield line

    return StreamingResponse(event_generator(), media_type="text/event-stream")


app.include_router(auth.router)
app.include_router(personas.router)
app.include_router(sessions.router)
app.include_router(documents.router)
app.include_router(voices.router)
app.include_router(analytics.router)
app.include_router(ws_router)
app.include_router(test.router)
