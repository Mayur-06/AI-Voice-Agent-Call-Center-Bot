import asyncio
from supabase import create_client, Client
from sqlalchemy import Column, String, Integer, Float, BigInteger, DateTime, Text, Boolean, ForeignKey
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime, timezone
from app.config import settings
from app.database import Base


_sync_client = create_client(settings.supabase_url, settings.supabase_anon_key)
_sync_admin_client = create_client(settings.supabase_url, settings.supabase_service_role_key)


def get_supabase() -> Client:
    return _sync_client


def get_supabase_admin() -> Client:
    return _sync_admin_client


def get_storage_admin():
    return _sync_admin_client.storage


async def run_supabase(query_builder):
    """Run a synchronous Supabase query in a thread pool."""
    return await asyncio.to_thread(query_builder)


class Persona(Base):
    __tablename__ = "personas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text)
    system_prompt = Column(Text, nullable=False)
    voice_id = Column(String, nullable=False)
    domain = Column(String)
    avatar_url = Column(String)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class Session(Base):
    __tablename__ = "sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=True)
    persona_id = Column(UUID(as_uuid=True), ForeignKey("personas.id"), nullable=False)
    status = Column(String, nullable=False, server_default=sa_text("'active'"))
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    ended_at = Column(DateTime(timezone=True))
    duration = Column(Float)
    selected_voice = Column(String)

    messages = relationship("Message", back_populates="session", order_by="Message.sequence_number")


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    speaker = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    audio_url = Column(String)
    recording_start_ms = Column(Integer)
    recording_end_ms = Column(Integer)
    sentiment = Column(String)
    latency_ms = Column(Integer)
    stt_latency_ms = Column(Integer)
    llm_latency_ms = Column(Integer)
    tts_first_audio_latency_ms = Column(Integer)
    sequence_number = Column(Integer, nullable=False)

    session = relationship("Session", back_populates="messages")


class Voice(Base):
    __tablename__ = "voices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    voice_id = Column(String, nullable=False)
    language = Column(String, nullable=False)
    preview_url = Column(String)


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=True)
    filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    storage_path = Column(String, nullable=False)
    status = Column(String, nullable=False, server_default=sa_text("'uploaded'"))
    uploaded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    chunks = relationship("DocumentChunk", back_populates="document", order_by="DocumentChunk.id")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_text = Column(Text, nullable=False)
    embedding_id = Column(String)
    chunk_metadata = Column("metadata", JSONB, server_default=sa_text("'{}'::jsonb"))

    document = relationship("Document", back_populates="chunks")


class SentimentRecord(Base):
    __tablename__ = "sentiment_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    sentiment = Column(String, nullable=False)
    score = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class CallMetric(Base):
    __tablename__ = "call_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, unique=True)
    total_duration = Column(Float, nullable=False)
    user_speaking_time = Column(Float, nullable=False)
    agent_speaking_time = Column(Float, nullable=False)
    turn_count = Column(Integer, nullable=False)
    average_latency = Column(Float, nullable=False)
    sentiment_score = Column(Float)
    resolution_status = Column(String)


class Recording(Base):
    __tablename__ = "recordings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    storage_path = Column(String, nullable=False)
    duration = Column(Float, nullable=False)
    file_size = Column(BigInteger, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
