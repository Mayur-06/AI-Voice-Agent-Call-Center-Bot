"""add summary and recording_url to sessions

Revision ID: 000000000004
Revises: 000000000003
Create Date: 2026-09-09 06:56:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '000000000004'
down_revision: Union[str, Sequence[str], None] = '000000000003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column("sessions", sa.Column("recording_url", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("sessions", "recording_url")
    op.drop_column("sessions", "summary")
