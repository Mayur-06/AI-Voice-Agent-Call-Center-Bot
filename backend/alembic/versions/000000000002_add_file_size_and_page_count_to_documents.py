"""add file_size and page_count to documents

Revision ID: 000000000002
Revises: 000000000001
Create Date: 2026-09-08 06:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '000000000002'
down_revision: Union[str, Sequence[str], None] = '000000000001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("file_size", sa.BigInteger(), nullable=True))
    op.add_column("documents", sa.Column("page_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "page_count")
    op.drop_column("documents", "file_size")
