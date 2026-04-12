-- ============================================================
-- 나의 제자 (My Jeja) — PostgreSQL 스키마 v3
-- 변경사항:
--   [OAuth] password_hash 제거
--           google_id, name, profile_image, refresh_token 추가
-- ============================================================

-- ============================================================
-- 1. 사용자 계정 (구글 OAuth2 전용)
-- ============================================================
-- 로그인 플로우:
--   ① 구글 OAuth 콜백에서 google_id, email, name, profile_image 수신
--   ② users 테이블 upsert (google_id 기준)
--   ③ JWT 발급 후 클라이언트 전달
--   ④ refresh_token은 재발급 시 갱신
-- ============================================================
CREATE TABLE users (
  id              UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
  email           TEXT      UNIQUE NOT NULL,
  google_id       TEXT      UNIQUE NOT NULL,  -- 구글 고유 식별자 (절대 변하지 않음)
  name            TEXT,                        -- 구글 표시 이름
  profile_image   TEXT,                        -- 구글 프로필 사진 URL
  refresh_token   TEXT,                        -- JWT 재발급용 (로그아웃 시 NULL 처리)
  created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 2. 과목
-- ============================================================
CREATE TABLE subjects (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name        TEXT        NOT NULL,
  description TEXT,
  created_at  TIMESTAMP   NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 3. 커리큘럼 항목
-- ============================================================
CREATE TABLE curriculum_items (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  subject_id  UUID        NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  title       TEXT        NOT NULL,
  note        TEXT,
  order_index INT         NOT NULL DEFAULT 0,
  created_at  TIMESTAMP   NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 4. 단계
-- ============================================================
CREATE TABLE stages (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  subject_id  UUID        NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  name        TEXT        NOT NULL,
  order_index INT         NOT NULL DEFAULT 0,
  passed      BOOLEAN     NOT NULL DEFAULT FALSE,
  passed_at   TIMESTAMP,
  created_at  TIMESTAMP   NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 5. 단계 ↔ 커리큘럼 항목 연결 (N:M)
-- ============================================================
CREATE TABLE stage_curriculum_items (
  stage_id           UUID NOT NULL REFERENCES stages(id) ON DELETE CASCADE,
  curriculum_item_id UUID NOT NULL REFERENCES curriculum_items(id) ON DELETE CASCADE,
  PRIMARY KEY (stage_id, curriculum_item_id)
);

-- ============================================================
-- 6. AI 학생 페르소나 (과목당 1개)
-- ============================================================
CREATE TABLE personas (
  id               UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          UUID      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  subject_id       UUID      NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  name             TEXT      NOT NULL,
  personality      TEXT      NOT NULL
                             CHECK (personality IN ('curious','careful','clumsy','perfectionist')),
  current_stage_id UUID      REFERENCES stages(id),
  created_at       TIMESTAMP NOT NULL DEFAULT NOW(),
  UNIQUE (subject_id)
);

-- ============================================================
-- 7. 페르소나 지식 메모리 (에빙하우스 망각 곡선)
-- ============================================================
CREATE TABLE persona_memory (
  id                 UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
  persona_id         UUID      NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
  curriculum_item_id UUID      REFERENCES curriculum_items(id),
  concept            TEXT      NOT NULL,
  summary            TEXT,
  taught_count       INT       NOT NULL DEFAULT 1,
  stability          FLOAT     NOT NULL DEFAULT 1.0,
  last_taught_at     TIMESTAMP NOT NULL DEFAULT NOW(),
  created_at         TIMESTAMP NOT NULL DEFAULT NOW(),
  UNIQUE (persona_id, concept)
);

-- ============================================================
-- 8. 수업 세션
-- 세션 종료 시:
--   ① messages → Claude Haiku 요약 → persona_memory upsert
--   ② 품질 평가 → quality_score 저장
--   ③ 약점 개념 → weak_point_tags upsert:
--        INSERT INTO weak_point_tags (persona_id, concept, fail_count, last_failed_at)
--        VALUES (:persona_id, :concept, 1, NOW())
--        ON CONFLICT (persona_id, concept)
--        DO UPDATE SET
--          fail_count     = weak_point_tags.fail_count + 1,
--          last_failed_at = NOW();
--   ④ messages = [] 로 초기화
-- ============================================================
CREATE TABLE teaching_sessions (
  id                 UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
  persona_id         UUID      NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
  curriculum_item_id UUID      REFERENCES curriculum_items(id),
  concept            TEXT      NOT NULL,
  quality_score      SMALLINT  CHECK (quality_score BETWEEN 0 AND 100),
  messages           JSONB     NOT NULL DEFAULT '[]',
  summary_generated  BOOLEAN   NOT NULL DEFAULT FALSE,
  created_at         TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 9. 단계 시험
-- 채점 후 처리:
--   ① persona_answers에서 오답 question_id 추출
--   ② questions[].concept_tag 조회
--   ③ weak_point_tags upsert:
--        INSERT INTO weak_point_tags (persona_id, concept, fail_count, last_failed_at)
--        VALUES (:persona_id, :concept_tag, 1, NOW())
--        ON CONFLICT (persona_id, concept)
--        DO UPDATE SET
--          fail_count     = weak_point_tags.fail_count + 1,
--          last_failed_at = NOW();
--   ④ passed = TRUE 이면:
--        UPDATE stages SET passed = TRUE, passed_at = NOW()
--        WHERE id = :stage_id;
-- ============================================================
CREATE TABLE exams (
  id              UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
  persona_id      UUID      NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
  stage_id        UUID      NOT NULL REFERENCES stages(id),
  questions       JSONB     NOT NULL,
  user_answers    JSONB     NOT NULL DEFAULT '[]',
  persona_answers JSONB     NOT NULL DEFAULT '[]',
  user_score      SMALLINT  CHECK (user_score BETWEEN 0 AND 100),
  persona_score   SMALLINT  CHECK (persona_score BETWEEN 0 AND 100),
  combined_score  SMALLINT  CHECK (combined_score BETWEEN 0 AND 100),
  passed          BOOLEAN,
  created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 10. 약점 태그 누적
-- teaching_sessions 종료 시 + exams 채점 시 두 경로에서 upsert
-- ============================================================
CREATE TABLE weak_point_tags (
  id             UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
  persona_id     UUID      NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
  concept        TEXT      NOT NULL,
  fail_count     INT       NOT NULL DEFAULT 1,
  last_failed_at TIMESTAMP NOT NULL DEFAULT NOW(),
  created_at     TIMESTAMP NOT NULL DEFAULT NOW(),
  UNIQUE (persona_id, concept)
);

-- ============================================================
-- 인덱스
-- ============================================================
CREATE INDEX idx_users_google_id      ON users(google_id);
CREATE INDEX idx_subjects_user        ON subjects(user_id);
CREATE INDEX idx_curriculum_subject   ON curriculum_items(subject_id, order_index);
CREATE INDEX idx_stages_subject       ON stages(subject_id, order_index);
CREATE INDEX idx_sci_curriculum_item  ON stage_curriculum_items(curriculum_item_id);
CREATE INDEX idx_personas_user        ON personas(user_id);
CREATE INDEX idx_memory_persona       ON persona_memory(persona_id);
CREATE INDEX idx_memory_last_taught   ON persona_memory(persona_id, last_taught_at);
CREATE INDEX idx_sessions_persona     ON teaching_sessions(persona_id, created_at DESC);
CREATE INDEX idx_sessions_item        ON teaching_sessions(curriculum_item_id);
CREATE INDEX idx_exams_persona        ON exams(persona_id, created_at DESC);
CREATE INDEX idx_exams_stage          ON exams(stage_id);
CREATE INDEX idx_weak_tags_persona    ON weak_point_tags(persona_id, fail_count DESC);
