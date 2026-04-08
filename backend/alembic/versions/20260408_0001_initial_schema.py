"""initial schema

Revision ID: 20260408_0001
Revises:
Create Date: 2026-04-08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260408_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use PostgreSQL-native enums with create_type disabled so table creation
    # never tries to emit duplicate CREATE TYPE statements.
    personality_type = postgresql.ENUM(
        "curious",
        "careful",
        "clumsy",
        "perfectionist",
        name="personality_type",
        create_type=False,
    )
    message_role = postgresql.ENUM("user", "assistant", name="message_role", create_type=False)
    exam_type = postgresql.ENUM("placement", "regular", name="exam_type", create_type=False)
    question_type = postgresql.ENUM("multiple_choice", "short_answer", name="question_type", create_type=False)

    # Partial deploys can leave enum types existing without all tables.
    # Create enums idempotently before creating tables.
    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE personality_type AS ENUM ('curious', 'careful', 'clumsy', 'perfectionist');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE message_role AS ENUM ('user', 'assistant');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE exam_type AS ENUM ('placement', 'regular');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE question_type AS ENUM ('multiple_choice', 'short_answer');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("users"):
        op.create_table(
            "users",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("email", sa.String(), nullable=False),
            sa.Column("password_hash", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("email"),
        )

    if not inspector.has_table("personas"):
        op.create_table(
            "personas",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("personality", personality_type, nullable=False),
            sa.Column("subject", sa.String(), nullable=False),
            sa.Column("current_level", sa.Integer(), nullable=False),
            sa.Column("placement_done", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("current_level BETWEEN 1 AND 9", name="chk_personas_level"),
            sa.CheckConstraint("subject = 'math'", name="chk_personas_subject_math"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", name="uq_personas_user_id"),
        )

    if not inspector.has_table("teaching_sessions"):
        op.create_table(
            "teaching_sessions",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("persona_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("concept", sa.String(), nullable=False),
            sa.Column("quality_score", sa.Integer(), nullable=True),
            sa.Column("predicted_retention", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["persona_id"], ["personas.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    if not inspector.has_table("teaching_messages"):
        op.create_table(
            "teaching_messages",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("role", message_role, nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["session_id"], ["teaching_sessions.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    if not inspector.has_table("weak_point_tags"):
        op.create_table(
            "weak_point_tags",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("persona_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("concept", sa.String(), nullable=False),
            sa.Column("fail_count", sa.Integer(), nullable=False),
            sa.Column("last_failed_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["persona_id"], ["personas.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("persona_id", "concept", name="uq_weak_point_persona_concept"),
        )

    if not inspector.has_table("exams"):
        op.create_table(
            "exams",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("persona_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("exam_type", exam_type, nullable=False),
            sa.Column("level", sa.Integer(), nullable=False),
            sa.Column("user_score", sa.Integer(), nullable=True),
            sa.Column("persona_score", sa.Integer(), nullable=True),
            sa.Column("combined_score", sa.Integer(), nullable=True),
            sa.Column("passed", sa.Boolean(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("level BETWEEN 1 AND 9", name="chk_exams_level"),
            sa.ForeignKeyConstraint(["persona_id"], ["personas.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    if not inspector.has_table("exam_questions"):
        op.create_table(
            "exam_questions",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("exam_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("question_no", sa.Integer(), nullable=False),
            sa.Column("type", question_type, nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("answer_key", sa.Text(), nullable=True),
            sa.Column("concept_tag", sa.String(), nullable=False),
            sa.Column("difficulty", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["exam_id"], ["exams.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("exam_id", "question_no", name="uq_exam_question_no"),
        )

    if not inspector.has_table("exam_answers"):
        op.create_table(
            "exam_answers",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("actor", sa.String(), nullable=False),
            sa.Column("answer", sa.Text(), nullable=False),
            sa.Column("thought", sa.Text(), nullable=True),
            sa.Column("is_correct", sa.Boolean(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["question_id"], ["exam_questions.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("question_id", "actor", name="uq_exam_answer_actor"),
        )

    op.execute("CREATE INDEX IF NOT EXISTS idx_personas_user_id ON personas (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sessions_persona_created ON teaching_sessions (persona_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_messages_session_created ON teaching_messages (session_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_weak_tags_persona_fail ON weak_point_tags (persona_id, fail_count)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_exams_persona_created ON exams (persona_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_exam_questions_exam_no ON exam_questions (exam_id, question_no)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_exam_answers_question_actor ON exam_answers (question_id, actor)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_exam_answers_question_actor")
    op.execute("DROP INDEX IF EXISTS idx_exam_questions_exam_no")
    op.execute("DROP INDEX IF EXISTS idx_exams_persona_created")
    op.execute("DROP INDEX IF EXISTS idx_weak_tags_persona_fail")
    op.execute("DROP INDEX IF EXISTS idx_messages_session_created")
    op.execute("DROP INDEX IF EXISTS idx_sessions_persona_created")
    op.execute("DROP INDEX IF EXISTS idx_personas_user_id")

    op.execute("DROP TABLE IF EXISTS exam_answers")
    op.execute("DROP TABLE IF EXISTS exam_questions")
    op.execute("DROP TABLE IF EXISTS exams")
    op.execute("DROP TABLE IF EXISTS weak_point_tags")
    op.execute("DROP TABLE IF EXISTS teaching_messages")
    op.execute("DROP TABLE IF EXISTS teaching_sessions")
    op.execute("DROP TABLE IF EXISTS personas")
    op.execute("DROP TABLE IF EXISTS users")

    bind = op.get_bind()
    sa.Enum(name="question_type").drop(bind, checkfirst=True)
    sa.Enum(name="exam_type").drop(bind, checkfirst=True)
    sa.Enum(name="message_role").drop(bind, checkfirst=True)
    sa.Enum(name="personality_type").drop(bind, checkfirst=True)
