"""initial clean schema (v2 squash)

Revision ID: 20260411_0001
Revises:
Create Date: 2026-04-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260411_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── personality_type enum ─────────────────────────────────────────────
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE personality_type AS ENUM ('curious', 'careful', 'clumsy', 'perfectionist');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    bind = op.get_bind()
    inspector = sa.inspect(bind)

    personality_type = postgresql.ENUM(
        "curious", "careful", "clumsy", "perfectionist",
        name="personality_type",
        create_type=False,
    )

    # ── users ─────────────────────────────────────────────────────────────
    if not inspector.has_table("users"):
        op.create_table(
            "users",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("email", sa.String(), unique=True, nullable=False),
            sa.Column("google_id", sa.String(), unique=True, nullable=True),
            sa.Column("name", sa.String(), nullable=True),
            sa.Column("profile_image", sa.String(), nullable=True),
            sa.Column("password_hash", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

    # ── subjects ──────────────────────────────────────────────────────────
    if not inspector.has_table("subjects"):
        op.create_table(
            "subjects",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

    # ── curriculum_items ──────────────────────────────────────────────────
    if not inspector.has_table("curriculum_items"):
        op.create_table(
            "curriculum_items",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("subject_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

    # ── stages ────────────────────────────────────────────────────────────
    if not inspector.has_table("stages"):
        op.create_table(
            "stages",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("subject_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("passed", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("passed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

    # ── stage_curriculum_items ────────────────────────────────────────────
    if not inspector.has_table("stage_curriculum_items"):
        op.create_table(
            "stage_curriculum_items",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("stage_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stages.id", ondelete="CASCADE"), nullable=False),
            sa.Column(
                "curriculum_item_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("curriculum_items.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.UniqueConstraint("stage_id", "curriculum_item_id", name="uq_stage_curriculum_item"),
        )

    # ── personas ──────────────────────────────────────────────────────────
    if not inspector.has_table("personas"):
        op.create_table(
            "personas",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("subject_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("current_stage_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stages.id"), nullable=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("personality", personality_type, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("subject_id", name="uq_personas_subject_id"),
        )

    # ── teaching_sessions ─────────────────────────────────────────────────
    if not inspector.has_table("teaching_sessions"):
        op.create_table(
            "teaching_sessions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("persona_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("personas.id", ondelete="CASCADE"), nullable=False),
            sa.Column("curriculum_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("curriculum_items.id"), nullable=True),
            sa.Column("concept", sa.String(), nullable=False),
            sa.Column("quality_score", sa.Integer(), nullable=True),
            sa.Column("weak_points", postgresql.JSONB(), nullable=False, server_default="'[]'"),
            sa.Column("messages", postgresql.JSONB(), nullable=False, server_default="'[]'"),
            sa.Column("summary_generated", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

    # ── weak_point_tags ───────────────────────────────────────────────────
    if not inspector.has_table("weak_point_tags"):
        op.create_table(
            "weak_point_tags",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("persona_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("personas.id", ondelete="CASCADE"), nullable=False),
            sa.Column("concept", sa.String(), nullable=False),
            sa.Column("fail_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("last_failed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("persona_id", "concept", name="uq_weak_point_persona_concept"),
        )

    # ── persona_memory ────────────────────────────────────────────────────
    if not inspector.has_table("persona_memory"):
        op.create_table(
            "persona_memory",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("persona_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("personas.id", ondelete="CASCADE"), nullable=False),
            sa.Column("curriculum_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("curriculum_items.id"), nullable=True),
            sa.Column("concept", sa.String(), nullable=False),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("taught_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("stability", sa.Float(), nullable=False, server_default="1.0"),
            sa.Column("last_taught_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("persona_id", "concept", name="uq_persona_memory_persona_concept"),
        )

    # ── exams ─────────────────────────────────────────────────────────────
    if not inspector.has_table("exams"):
        op.create_table(
            "exams",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("persona_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("personas.id", ondelete="CASCADE"), nullable=False),
            sa.Column("stage_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stages.id"), nullable=False),
            sa.Column("questions", postgresql.JSONB(), nullable=False, server_default="'[]'"),
            sa.Column("user_answers", postgresql.JSONB(), nullable=False, server_default="'[]'"),
            sa.Column("persona_answers", postgresql.JSONB(), nullable=False, server_default="'[]'"),
            sa.Column("user_score", sa.Integer(), nullable=True),
            sa.Column("persona_score", sa.Integer(), nullable=True),
            sa.Column("combined_score", sa.Integer(), nullable=True),
            sa.Column("passed", sa.Boolean(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

    # ── indexes ───────────────────────────────────────────────────────────
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_google_id        ON users(google_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_subjects_user          ON subjects(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_curriculum_subject     ON curriculum_items(subject_id, order_index)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_stages_subject         ON stages(subject_id, order_index)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sci_curriculum_item    ON stage_curriculum_items(curriculum_item_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_personas_user          ON personas(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_memory_persona         ON persona_memory(persona_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_memory_last_taught     ON persona_memory(persona_id, last_taught_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sessions_persona       ON teaching_sessions(persona_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sessions_item          ON teaching_sessions(curriculum_item_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_exams_persona          ON exams(persona_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_exams_stage            ON exams(stage_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_weak_tags_persona      ON weak_point_tags(persona_id, fail_count DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS exams CASCADE")
    op.execute("DROP TABLE IF EXISTS persona_memory CASCADE")
    op.execute("DROP TABLE IF EXISTS weak_point_tags CASCADE")
    op.execute("DROP TABLE IF EXISTS teaching_sessions CASCADE")
    op.execute("DROP TABLE IF EXISTS personas CASCADE")
    op.execute("DROP TABLE IF EXISTS stage_curriculum_items CASCADE")
    op.execute("DROP TABLE IF EXISTS stages CASCADE")
    op.execute("DROP TABLE IF EXISTS curriculum_items CASCADE")
    op.execute("DROP TABLE IF EXISTS subjects CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
    op.execute("DROP TYPE IF EXISTS personality_type")
