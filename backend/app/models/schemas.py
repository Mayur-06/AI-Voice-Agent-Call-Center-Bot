from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any


class Persona(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    system_prompt: str
    voice_id: str
    domain: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class PersonaCreate(BaseModel):
    name: str
    description: Optional[str] = None
    system_prompt: str
    voice_id: str
    domain: Optional[str] = None
    avatar_url: Optional[str] = None


class Session(BaseModel):
    id: str
    user_id: Optional[str] = None
    persona_id: str
    status: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration: Optional[float] = None
    selected_voice: Optional[str] = None


class SessionCreate(BaseModel):
    persona_id: str
    user_id: Optional[str] = None
    status: Optional[str] = "active"
    selected_voice: Optional[str] = None


class Message(BaseModel):
    id: str
    session_id: str
    speaker: str
    text: str
    timestamp: datetime
    audio_url: Optional[str] = None
    recording_start_ms: Optional[int] = None
    recording_end_ms: Optional[int] = None
    sentiment: Optional[str] = None
    latency_ms: Optional[int] = None
    stt_latency_ms: Optional[int] = None
    llm_latency_ms: Optional[int] = None
    tts_first_audio_latency_ms: Optional[int] = None
    sequence_number: int


class MessageRequest(BaseModel):
    text: str


class Voice(BaseModel):
    id: str
    name: str
    voice_id: str
    language: str
    preview_url: Optional[str] = None


class Document(BaseModel):
    id: str
    session_id: str
    filename: str
    file_type: str
    storage_path: str
    status: str
    uploaded_at: datetime


class DocumentChunk(BaseModel):
    id: str
    document_id: str
    chunk_text: str
    embedding_id: Optional[str] = None
    metadata: Dict[str, Any] = {}


class SentimentRecord(BaseModel):
    id: str
    session_id: str
    message_id: str
    sentiment: str
    score: float
    created_at: datetime


class CallMetric(BaseModel):
    id: str
    session_id: str
    total_duration: float
    user_speaking_time: float
    agent_speaking_time: float
    turn_count: int
    average_latency: float
    sentiment_score: Optional[float] = None
    resolution_status: Optional[str] = None


class Recording(BaseModel):
    id: str
    session_id: str
    storage_path: str
    duration: float
    file_size: int
    created_at: datetime


class Analytics(BaseModel):
    total_sessions: int
    total_turns: int
    avg_latency_ms: float
    interruption_count: int
    avg_session_duration_s: float
    sentiment_breakdown: Dict[str, int]
