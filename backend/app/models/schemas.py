from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any


class Persona(BaseModel):
    id: str
    name: str
    system_prompt: str
    voice_id: str
    voice_settings: Dict[str, Any] = {}
    created_at: datetime


class PersonaCreate(BaseModel):
    name: str
    system_prompt: str
    voice_id: str
    voice_settings: Dict[str, Any] = {}


class Session(BaseModel):
    id: str
    persona_id: str
    user_id: Optional[str] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    metadata: Dict[str, Any] = {}


class SessionCreate(BaseModel):
    persona_id: str
    metadata: Dict[str, Any] = {}


class Turn(BaseModel):
    id: str
    session_id: str
    speaker: str
    text: str
    audio_ref: Optional[str] = None
    sentiment: Optional[str] = None
    timestamp: datetime
    latency_ms: Optional[int] = None
    interrupted: bool = False


class Document(BaseModel):
    id: str
    persona_id: str
    filename: str
    chunks_count: int
    created_at: datetime


class DocumentChunk(BaseModel):
    id: str
    document_id: str
    chunk_text: str
    embedding_id: Optional[str] = None


class Voice(BaseModel):
    voice_id: str
    name: str
    category: str
    preview_url: Optional[str] = None


class Analytics(BaseModel):
    total_sessions: int
    total_turns: int
    avg_latency_ms: float
    interruption_count: int
    avg_session_duration_s: float
    sentiment_breakdown: Dict[str, int]


class MessageRequest(BaseModel):
    text: str
