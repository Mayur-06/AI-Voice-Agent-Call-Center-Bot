"""add session document associations

Revision ID: 000000000005
Revises: 000000000004
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "000000000005"
down_revision: Union[str, Sequence[str], None] = "000000000004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "session_documents",
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("attached_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_session_documents_document_id", "session_documents", ["document_id"])


def downgrade() -> None:
    op.drop_index("idx_session_documents_document_id", table_name="session_documents")
    op.drop_table("session_documents")
