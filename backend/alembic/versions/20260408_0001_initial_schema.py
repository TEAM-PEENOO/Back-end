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
    personality_type = sa.Enum("curious", "careful", "clumsy", "perfectionist", name="personality_type")
    message_role = sa.Enum("user", "assistant", name="message_role")
    exam_type = sa.Enum("placement", "regular", name="exam_type")
    question_type = sa.Enum("multiple_choice", "short_answer", name="question_type")

    bind = op.get_bind()
    personality_type.create(bind, checkfirst=True)
    message_role.create(bind, checkfirst=True)
    exam_type.create(bind, checkfirst=True)
    question_type.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

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

    op.create_index("idx_personas_user_id", "personas", ["user_id"], unique=False)
    op.create_index("idx_sessions_persona_created", "teaching_sessions", ["persona_id", "created_at"], unique=False)
    op.create_index("idx_messages_session_created", "teaching_messages", ["session_id", "created_at"], unique=False)
    op.create_index("idx_weak_tags_persona_fail", "weak_point_tags", ["persona_id", "fail_count"], unique=False)
    op.create_index("idx_exams_persona_created", "exams", ["persona_id", "created_at"], unique=False)
    op.create_index("idx_exam_questions_exam_no", "exam_questions", ["exam_id", "question_no"], unique=False)
    op.create_index("idx_exam_answers_question_actor", "exam_answers", ["question_id", "actor"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_exam_answers_question_actor", table_name="exam_answers")
    op.drop_index("idx_exam_questions_exam_no", table_name="exam_questions")
    op.drop_index("idx_exams_persona_created", table_name="exams")
    op.drop_index("idx_weak_tags_persona_fail", table_name="weak_point_tags")
    op.drop_index("idx_messages_session_created", table_name="teaching_messages")
    op.drop_index("idx_sessions_persona_created", table_name="teaching_sessions")
    op.drop_index("idx_personas_user_id", table_name="personas")

    op.drop_table("exam_answers")
    op.drop_table("exam_questions")
    op.drop_table("exams")
    op.drop_table("weak_point_tags")
    op.drop_table("teaching_messages")
    op.drop_table("teaching_sessions")
    op.drop_table("personas")
    op.drop_table("users")

    bind = op.get_bind()
    sa.Enum(name="question_type").drop(bind, checkfirst=True)
    sa.Enum(name="exam_type").drop(bind, checkfirst=True)
    sa.Enum(name="message_role").drop(bind, checkfirst=True)
    sa.Enum(name="personality_type").drop(bind, checkfirst=True)
