-- My Jeja MVP database schema
-- Scope: math only, level 1-9 (grade school 1 -> middle school 3)
-- Security policy: exam answer keys are deleted right after grading

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'personality_type') THEN
    CREATE TYPE personality_type AS ENUM ('curious', 'careful', 'clumsy', 'perfectionist');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'exam_type') THEN
    CREATE TYPE exam_type AS ENUM ('placement', 'regular');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'question_type') THEN
    CREATE TYPE question_type AS ENUM ('multiple_choice', 'short_answer');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'message_role') THEN
    CREATE TYPE message_role AS ENUM ('user', 'assistant');
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS personas (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  personality personality_type NOT NULL,
  subject TEXT NOT NULL DEFAULT 'math' CHECK (subject = 'math'),
  current_level INT NOT NULL DEFAULT 1 CHECK (current_level BETWEEN 1 AND 9),
  placement_done BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id)
);

CREATE TABLE IF NOT EXISTS persona_concepts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  persona_id UUID NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
  concept TEXT NOT NULL,
  taught_count INT NOT NULL DEFAULT 1 CHECK (taught_count >= 1),
  stability DOUBLE PRECISION NOT NULL DEFAULT 1.0 CHECK (stability > 0),
  last_taught_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (persona_id, concept)
);

CREATE TABLE IF NOT EXISTS weak_point_tags (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  persona_id UUID NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
  concept TEXT NOT NULL,
  fail_count INT NOT NULL DEFAULT 1 CHECK (fail_count >= 1),
  last_failed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (persona_id, concept)
);
-- Single source of truth for weak points:
-- - teaching session weak points are upserted here
-- - exam wrong answers are upserted here

CREATE TABLE IF NOT EXISTS teaching_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  persona_id UUID NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
  concept TEXT NOT NULL,
  quality_score INT CHECK (quality_score BETWEEN 0 AND 100),
  predicted_retention DOUBLE PRECISION CHECK (predicted_retention BETWEEN 0 AND 1),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS teaching_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL REFERENCES teaching_sessions(id) ON DELETE CASCADE,
  role message_role NOT NULL,
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS exams (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  persona_id UUID NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
  exam_type exam_type NOT NULL,
  level INT NOT NULL CHECK (level BETWEEN 1 AND 9),
  user_score INT CHECK (user_score BETWEEN 0 AND 100),
  persona_score INT CHECK (persona_score BETWEEN 0 AND 100),
  combined_score INT CHECK (combined_score BETWEEN 0 AND 100),
  passed BOOLEAN,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS exam_questions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  exam_id UUID NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
  question_no INT NOT NULL CHECK (question_no >= 1),
  type question_type NOT NULL,
  content TEXT NOT NULL,
  options JSONB,
  answer_key TEXT,
  concept_tag TEXT NOT NULL,
  difficulty INT NOT NULL CHECK (difficulty IN (1, 2, 3)),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (exam_id, question_no)
);

CREATE TABLE IF NOT EXISTS exam_answers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  question_id UUID NOT NULL REFERENCES exam_questions(id) ON DELETE CASCADE,
  actor TEXT NOT NULL CHECK (actor IN ('user', 'persona')),
  answer TEXT NOT NULL,
  thought TEXT,
  is_correct BOOLEAN,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (question_id, actor)
);
-- Application flow requirement:
-- when a user answer is wrong during grading, upsert weak_point_tags(persona_id, concept)

CREATE INDEX IF NOT EXISTS idx_personas_user_id ON personas(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_persona_created ON teaching_sessions(persona_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_session_created ON teaching_messages(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_weak_tags_persona_fail ON weak_point_tags(persona_id, fail_count DESC);
CREATE INDEX IF NOT EXISTS idx_exams_persona_created ON exams(persona_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_exam_questions_exam_no ON exam_questions(exam_id, question_no);
CREATE INDEX IF NOT EXISTS idx_exam_answers_question_actor ON exam_answers(question_id, actor);

-- Security helper function:
-- remove answer keys after grading is finished.
CREATE OR REPLACE FUNCTION purge_exam_answer_keys(p_exam_id UUID)
RETURNS VOID AS $$
BEGIN
  UPDATE exam_questions
  SET answer_key = NULL
  WHERE exam_id = p_exam_id;
END;
$$ LANGUAGE plpgsql;
