"""add p95_latency and stream_status to call_metrics

Revision ID: 000000000003
Revises: 000000000002
Create Date: 2026-09-09 05:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '000000000003'
down_revision: Union[str, Sequence[str], None] = '000000000002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("call_metrics", sa.Column("p95_latency", sa.Float(), nullable=True))
    op.add_column("call_metrics", sa.Column("stream_status", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("call_metrics", "stream_status")
    op.drop_column("call_metrics", "p95_latency")
