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
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("subjects"):
        op.create_table(
            "subjects",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )

    if not inspector.has_table("curriculum_items"):
        op.create_table(
            "curriculum_items",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("subject_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )

    if not inspector.has_table("stages"):
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

    if not inspector.has_table("stage_curriculum_items"):
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

    persona_columns = {c["name"] for c in inspector.get_columns("personas")}
    if "subject_id" not in persona_columns:
        op.add_column("personas", sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=True))
    if "current_stage_id" not in persona_columns:
        op.add_column("personas", sa.Column("current_stage_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_personas_subject_id'
            ) THEN
                ALTER TABLE personas
                ADD CONSTRAINT fk_personas_subject_id
                FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_personas_current_stage_id'
            ) THEN
                ALTER TABLE personas
                ADD CONSTRAINT fk_personas_current_stage_id
                FOREIGN KEY (current_stage_id) REFERENCES stages(id);
            END IF;
        END $$;
        """
    )

    session_columns = {c["name"] for c in inspector.get_columns("teaching_sessions")}
    if "curriculum_item_id" not in session_columns:
        op.add_column("teaching_sessions", sa.Column("curriculum_item_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_teaching_sessions_curriculum_item_id'
            ) THEN
                ALTER TABLE teaching_sessions
                ADD CONSTRAINT fk_teaching_sessions_curriculum_item_id
                FOREIGN KEY (curriculum_item_id) REFERENCES curriculum_items(id);
            END IF;
        END $$;
        """
    )

    exam_columns = {c["name"] for c in inspector.get_columns("exams")}
    if "stage_id" not in exam_columns:
        op.add_column("exams", sa.Column("stage_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_exams_stage_id'
            ) THEN
                ALTER TABLE exams
                ADD CONSTRAINT fk_exams_stage_id
                FOREIGN KEY (stage_id) REFERENCES stages(id);
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE exams DROP CONSTRAINT IF EXISTS fk_exams_stage_id")
    op.execute("ALTER TABLE exams DROP COLUMN IF EXISTS stage_id")

    op.execute("ALTER TABLE teaching_sessions DROP CONSTRAINT IF EXISTS fk_teaching_sessions_curriculum_item_id")
    op.execute("ALTER TABLE teaching_sessions DROP COLUMN IF EXISTS curriculum_item_id")

    op.execute("ALTER TABLE personas DROP CONSTRAINT IF EXISTS fk_personas_current_stage_id")
    op.execute("ALTER TABLE personas DROP CONSTRAINT IF EXISTS fk_personas_subject_id")
    op.execute("ALTER TABLE personas DROP COLUMN IF EXISTS current_stage_id")
    op.execute("ALTER TABLE personas DROP COLUMN IF EXISTS subject_id")

    op.execute("DROP TABLE IF EXISTS stage_curriculum_items")
    op.execute("DROP TABLE IF EXISTS stages")
    op.execute("DROP TABLE IF EXISTS curriculum_items")
    op.execute("DROP TABLE IF EXISTS subjects")
