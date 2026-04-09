"""reset schema to v2 subject-persona design

Revision ID: 20260410_0007
Revises: 20260409_0006
Create Date: 2026-04-10 03:10:00
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260410_0007"
down_revision: Union[str, Sequence[str], None] = "20260409_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Persona enum: v2 keeps only 4 personalities.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'personality_type')
             AND NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'personality_type_old') THEN
            ALTER TYPE personality_type RENAME TO personality_type_old;
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'personality_type') THEN
            CREATE TYPE personality_type AS ENUM ('curious', 'careful', 'clumsy', 'perfectionist');
          END IF;
        END $$;
        """
    )
    op.execute("UPDATE personas SET personality = 'curious' WHERE personality::text = 'steady'")
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'personality_type_old') THEN
            ALTER TABLE personas
            ALTER COLUMN personality TYPE personality_type
            USING personality::text::personality_type;
            DROP TYPE personality_type_old;
          END IF;
        END $$;
        """
    )

    # Normalize v2 persona constraints.
    op.execute("ALTER TABLE personas DROP CONSTRAINT IF EXISTS uq_personas_user_id")
    op.execute("ALTER TABLE personas DROP CONSTRAINT IF EXISTS chk_personas_subject_math")
    op.execute("ALTER TABLE personas DROP CONSTRAINT IF EXISTS chk_personas_level")
    op.execute("ALTER TABLE personas ALTER COLUMN subject_id SET NOT NULL")
    op.execute("ALTER TABLE personas ADD CONSTRAINT uq_personas_subject_id UNIQUE (subject_id)")

    # Replace persona_concepts -> persona_memory (v2 naming + fields)
    op.execute("ALTER TABLE persona_concepts RENAME TO persona_memory")
    op.execute("ALTER TABLE persona_memory RENAME CONSTRAINT uq_persona_concepts_persona_concept TO uq_persona_memory_persona_concept")
    op.execute("ALTER TABLE persona_memory ADD COLUMN IF NOT EXISTS curriculum_item_id UUID REFERENCES curriculum_items(id)")
    op.execute("ALTER TABLE persona_memory ADD COLUMN IF NOT EXISTS summary TEXT")
    op.execute("ALTER TABLE persona_memory ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()")

    # Collapse teaching_messages into teaching_sessions.messages JSONB.
    op.execute("ALTER TABLE teaching_sessions ADD COLUMN IF NOT EXISTS weak_points JSONB NOT NULL DEFAULT '[]'")
    op.execute("ALTER TABLE teaching_sessions ADD COLUMN IF NOT EXISTS messages JSONB NOT NULL DEFAULT '[]'")
    op.execute("ALTER TABLE teaching_sessions ADD COLUMN IF NOT EXISTS summary_generated BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE teaching_sessions DROP COLUMN IF EXISTS predicted_retention")
    op.execute("DROP TABLE IF EXISTS teaching_messages")
    op.execute("DROP TYPE IF EXISTS message_role")

    # Replace normalized exam tables with JSONB exam payload fields.
    op.execute("ALTER TABLE exams DROP COLUMN IF EXISTS exam_type")
    op.execute("ALTER TABLE exams DROP COLUMN IF EXISTS level")
    op.execute("ALTER TABLE exams ALTER COLUMN stage_id SET NOT NULL")
    op.execute("ALTER TABLE exams ADD COLUMN IF NOT EXISTS questions JSONB NOT NULL DEFAULT '[]'")
    op.execute("ALTER TABLE exams ADD COLUMN IF NOT EXISTS user_answers JSONB NOT NULL DEFAULT '[]'")
    op.execute("ALTER TABLE exams ADD COLUMN IF NOT EXISTS persona_answers JSONB NOT NULL DEFAULT '[]'")
    op.execute("DROP TABLE IF EXISTS exam_answers")
    op.execute("DROP TABLE IF EXISTS exam_questions")
    op.execute("DROP TYPE IF EXISTS question_type")
    op.execute("DROP TYPE IF EXISTS exam_type")

    # weak_point_tags created_at required by v2 spec
    op.execute("ALTER TABLE weak_point_tags ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()")

    # V2 supporting indexes
    op.execute("CREATE INDEX IF NOT EXISTS idx_subjects_user ON subjects(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_curriculum_subject ON curriculum_items(subject_id, order_index)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_stages_subject ON stages(subject_id, order_index)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sci_curriculum_item ON stage_curriculum_items(curriculum_item_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_personas_user ON personas(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_memory_persona ON persona_memory(persona_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_memory_last_taught ON persona_memory(persona_id, last_taught_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sessions_persona ON teaching_sessions(persona_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sessions_item ON teaching_sessions(curriculum_item_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_exams_persona ON exams(persona_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_exams_stage ON exams(stage_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_weak_tags_persona ON weak_point_tags(persona_id, fail_count DESC)")


def downgrade() -> None:
    raise RuntimeError("Downgrade is not supported for 20260410_0007 reset migration.")
