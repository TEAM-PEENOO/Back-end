-- My Jeja v2 database schema
-- Source of truth: DB_Schema.md (subject-scoped design)

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'personality_type') THEN
    CREATE TYPE personality_type AS ENUM ('curious', 'careful', 'clumsy', 'perfectionist');
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS subjects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS curriculum_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  subject_id UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  note TEXT,
  order_index INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS stages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  subject_id UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  order_index INT NOT NULL DEFAULT 0,
  passed BOOLEAN NOT NULL DEFAULT FALSE,
  passed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS stage_curriculum_items (
  stage_id UUID NOT NULL REFERENCES stages(id) ON DELETE CASCADE,
  curriculum_item_id UUID NOT NULL REFERENCES curriculum_items(id) ON DELETE CASCADE,
  PRIMARY KEY (stage_id, curriculum_item_id)
);

CREATE TABLE IF NOT EXISTS personas (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  subject_id UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  personality personality_type NOT NULL,
  current_stage_id UUID REFERENCES stages(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (subject_id)
);

CREATE TABLE IF NOT EXISTS persona_memory (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  persona_id UUID NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
  curriculum_item_id UUID REFERENCES curriculum_items(id),
  concept TEXT NOT NULL,
  summary TEXT,
  taught_count INT NOT NULL DEFAULT 1,
  stability DOUBLE PRECISION NOT NULL DEFAULT 1.0,
  last_taught_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (persona_id, concept)
);

CREATE TABLE IF NOT EXISTS teaching_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  persona_id UUID NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
  curriculum_item_id UUID REFERENCES curriculum_items(id),
  concept TEXT NOT NULL,
  quality_score SMALLINT CHECK (quality_score BETWEEN 0 AND 100),
  weak_points JSONB NOT NULL DEFAULT '[]',
  messages JSONB NOT NULL DEFAULT '[]',
  summary_generated BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS exams (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  persona_id UUID NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
  stage_id UUID NOT NULL REFERENCES stages(id),
  questions JSONB NOT NULL,
  user_answers JSONB NOT NULL DEFAULT '[]',
  persona_answers JSONB NOT NULL DEFAULT '[]',
  user_score SMALLINT CHECK (user_score BETWEEN 0 AND 100),
  persona_score SMALLINT CHECK (persona_score BETWEEN 0 AND 100),
  combined_score SMALLINT CHECK (combined_score BETWEEN 0 AND 100),
  passed BOOLEAN,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS weak_point_tags (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  persona_id UUID NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
  concept TEXT NOT NULL,
  fail_count INT NOT NULL DEFAULT 1,
  last_failed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (persona_id, concept)
);

CREATE INDEX IF NOT EXISTS idx_subjects_user ON subjects(user_id);
CREATE INDEX IF NOT EXISTS idx_curriculum_subject ON curriculum_items(subject_id, order_index);
CREATE INDEX IF NOT EXISTS idx_stages_subject ON stages(subject_id, order_index);
CREATE INDEX IF NOT EXISTS idx_sci_curriculum_item ON stage_curriculum_items(curriculum_item_id);
CREATE INDEX IF NOT EXISTS idx_personas_user ON personas(user_id);
CREATE INDEX IF NOT EXISTS idx_memory_persona ON persona_memory(persona_id);
CREATE INDEX IF NOT EXISTS idx_memory_last_taught ON persona_memory(persona_id, last_taught_at);
CREATE INDEX IF NOT EXISTS idx_sessions_persona ON teaching_sessions(persona_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_item ON teaching_sessions(curriculum_item_id);
CREATE INDEX IF NOT EXISTS idx_exams_persona ON exams(persona_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_exams_stage ON exams(stage_id);
CREATE INDEX IF NOT EXISTS idx_weak_tags_persona ON weak_point_tags(persona_id, fail_count DESC);
