"""drop session_weak_points table

Revision ID: 20260409_0005
Revises: 20260408_0004
Create Date: 2026-04-09 01:15:00
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260409_0005"
down_revision = "20260408_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS session_weak_points")


def downgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS session_weak_points (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id UUID NOT NULL REFERENCES teaching_sessions(id) ON DELETE CASCADE,
            concept TEXT NOT NULL
        )
        """
    )
