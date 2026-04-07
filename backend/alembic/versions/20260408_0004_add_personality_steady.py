"""add steady personality enum value

Revision ID: 20260408_0004
Revises: 20260408_0003
Create Date: 2026-04-08
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260408_0004"
down_revision: Union[str, Sequence[str], None] = "20260408_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE personality_type ADD VALUE IF NOT EXISTS 'steady';")


def downgrade() -> None:
    # PostgreSQL enum values are not easily removed in-place.
    pass
