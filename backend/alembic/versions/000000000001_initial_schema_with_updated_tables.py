"""initial schema with updated table definitions

Revision ID: 000000000001
Revises: 
Create Date: 2026-08-31 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision: str = '000000000001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "personas",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String, nullable=False, unique=True),
        sa.Column("description", sa.Text),
        sa.Column("system_prompt", sa.Text, nullable=False),
        sa.Column("voice_id", sa.String, nullable=False),
        sa.Column("domain", sa.String),
        sa.Column("avatar_url", sa.String),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_personas_name", "personas", ["name"], unique=True)

    op.create_table(
        "sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("persona_id", UUID(as_uuid=True), sa.ForeignKey("personas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default=sa.text("'active'")),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("duration", sa.Float),
        sa.Column("selected_voice", sa.String),
    )
    op.create_index("idx_sessions_persona_id", "sessions", ["persona_id"])
    op.create_index("idx_sessions_user_id", "sessions", ["user_id"])

    op.create_table(
        "messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("speaker", sa.String, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("audio_url", sa.String),
        sa.Column("recording_start_ms", sa.Integer),
        sa.Column("recording_end_ms", sa.Integer),
        sa.Column("sentiment", sa.String),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("stt_latency_ms", sa.Integer),
        sa.Column("llm_latency_ms", sa.Integer),
        sa.Column("tts_first_audio_latency_ms", sa.Integer),
        sa.Column("sequence_number", sa.Integer, nullable=False),
    )
    op.create_index("idx_messages_session_id", "messages", ["session_id"])
    op.create_index("idx_messages_timestamp", "messages", ["timestamp"])

    op.create_table(
        "voices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("voice_id", sa.String, nullable=False),
        sa.Column("language", sa.String, nullable=False),
        sa.Column("preview_url", sa.String),
    )
    op.create_index("idx_voices_voice_id", "voices", ["voice_id"])

    op.create_table(
        "documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String, nullable=False),
        sa.Column("file_type", sa.String, nullable=False),
        sa.Column("storage_path", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default=sa.text("'uploaded'")),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_documents_session_id", "documents", ["session_id"])

    op.create_table(
        "document_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_text", sa.Text, nullable=False),
        sa.Column("embedding_id", sa.String),
        sa.Column("metadata", JSONB, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("idx_document_chunks_document_id", "document_chunks", ["document_id"])

    op.create_table(
        "sentiment_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", UUID(as_uuid=True), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sentiment", sa.String, nullable=False),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_sentiment_records_session_id", "sentiment_records", ["session_id"])
    op.create_index("idx_sentiment_records_message_id", "sentiment_records", ["message_id"])

    op.create_table(
        "call_metrics",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("total_duration", sa.Float, nullable=False),
        sa.Column("user_speaking_time", sa.Float, nullable=False),
        sa.Column("agent_speaking_time", sa.Float, nullable=False),
        sa.Column("turn_count", sa.Integer, nullable=False),
        sa.Column("average_latency", sa.Float, nullable=False),
        sa.Column("sentiment_score", sa.Float),
        sa.Column("resolution_status", sa.String),
    )
    op.create_index("idx_call_metrics_session_id", "call_metrics", ["session_id"], unique=True)

    op.create_table(
        "recordings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("storage_path", sa.String, nullable=False),
        sa.Column("duration", sa.Float, nullable=False),
        sa.Column("file_size", sa.BigInteger, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_recordings_session_id", "recordings", ["session_id"])


def downgrade() -> None:
    op.drop_index("idx_recordings_session_id", table_name="recordings")
    op.drop_table("recordings")
    op.drop_index("idx_call_metrics_session_id", table_name="call_metrics")
    op.drop_table("call_metrics")
    op.drop_index("idx_sentiment_records_message_id", table_name="sentiment_records")
    op.drop_index("idx_sentiment_records_session_id", table_name="sentiment_records")
    op.drop_table("sentiment_records")
    op.drop_index("idx_document_chunks_document_id", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_index("idx_documents_session_id", table_name="documents")
    op.drop_table("documents")
    op.drop_index("idx_voices_voice_id", table_name="voices")
    op.drop_table("voices")
    op.drop_index("idx_messages_timestamp", table_name="messages")
    op.drop_index("idx_messages_session_id", table_name="messages")
    op.drop_table("messages")
    op.drop_index("idx_sessions_user_id", table_name="sessions")
    op.drop_index("idx_sessions_persona_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("idx_personas_name", table_name="personas")
    op.drop_table("personas")
