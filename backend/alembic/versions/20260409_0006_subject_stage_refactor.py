"""add subject/stage/curriculum entities and foreign keys

Revision ID: 20260409_0006
Revises: 20260409_0005
Create Date: 2026-04-09 01:45:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260409_0006"
down_revision: Union[str, Sequence[str], None] = "20260409_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "subjects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "curriculum_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "stages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("passed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "stage_curriculum_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("stage_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stages.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "curriculum_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("curriculum_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint("stage_id", "curriculum_item_id", name="uq_stage_curriculum_item"),
    )

    op.add_column("personas", sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("personas", sa.Column("current_stage_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_personas_subject_id", "personas", "subjects", ["subject_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_personas_current_stage_id", "personas", "stages", ["current_stage_id"], ["id"])

    op.add_column("teaching_sessions", sa.Column("curriculum_item_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_teaching_sessions_curriculum_item_id",
        "teaching_sessions",
        "curriculum_items",
        ["curriculum_item_id"],
        ["id"],
    )

    op.add_column("exams", sa.Column("stage_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_exams_stage_id", "exams", "stages", ["stage_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_exams_stage_id", "exams", type_="foreignkey")
    op.drop_column("exams", "stage_id")

    op.drop_constraint("fk_teaching_sessions_curriculum_item_id", "teaching_sessions", type_="foreignkey")
    op.drop_column("teaching_sessions", "curriculum_item_id")

    op.drop_constraint("fk_personas_current_stage_id", "personas", type_="foreignkey")
    op.drop_constraint("fk_personas_subject_id", "personas", type_="foreignkey")
    op.drop_column("personas", "current_stage_id")
    op.drop_column("personas", "subject_id")

    op.drop_table("stage_curriculum_items")
    op.drop_table("stages")
    op.drop_table("curriculum_items")
    op.drop_table("subjects")
