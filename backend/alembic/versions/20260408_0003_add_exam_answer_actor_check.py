"""add exam_answers actor check constraint

Revision ID: 20260408_0003
Revises: 20260408_0002
Create Date: 2026-04-08
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260408_0003"
down_revision: Union[str, Sequence[str], None] = "20260408_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'chk_exam_answers_actor'
            ) THEN
                ALTER TABLE exam_answers
                ADD CONSTRAINT chk_exam_answers_actor
                CHECK (actor IN ('user','persona'));
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE exam_answers DROP CONSTRAINT IF EXISTS chk_exam_answers_actor;")
