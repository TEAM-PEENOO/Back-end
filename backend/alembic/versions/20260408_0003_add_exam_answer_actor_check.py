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
    op.create_check_constraint(
        "chk_exam_answers_actor",
        "exam_answers",
        "actor IN ('user','persona')",
    )


def downgrade() -> None:
    op.drop_constraint("chk_exam_answers_actor", "exam_answers", type_="check")
