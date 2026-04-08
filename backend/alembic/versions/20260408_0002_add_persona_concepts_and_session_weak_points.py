"""add persona_concepts and session_weak_points

Revision ID: 20260408_0002
Revises: 20260408_0001
Create Date: 2026-04-08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260408_0002"
down_revision: Union[str, Sequence[str], None] = "20260408_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("persona_concepts"):
        op.create_table(
            "persona_concepts",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("persona_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("concept", sa.String(), nullable=False),
            sa.Column("taught_count", sa.Integer(), nullable=False),
            sa.Column("stability", sa.Float(), nullable=False),
            sa.Column("last_taught_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["persona_id"], ["personas.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("persona_id", "concept", name="uq_persona_concepts_persona_concept"),
        )
    op.execute("CREATE INDEX IF NOT EXISTS idx_persona_concepts_persona ON persona_concepts (persona_id)")

    if not inspector.has_table("session_weak_points"):
        op.create_table(
            "session_weak_points",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("concept", sa.String(), nullable=False),
            sa.ForeignKeyConstraint(["session_id"], ["teaching_sessions.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    op.execute("CREATE INDEX IF NOT EXISTS idx_session_weak_points_session ON session_weak_points (session_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_session_weak_points_session")
    op.execute("DROP TABLE IF EXISTS session_weak_points")
    op.execute("DROP INDEX IF EXISTS idx_persona_concepts_persona")
    op.execute("DROP TABLE IF EXISTS persona_concepts")
