# DB 스키마 설계 — 나의 제자 (My Jeja)

> 기반 문서: `proposal.md` (v2), `main_logic.md`, `AI_API_Architecture.md`
> DB 엔진: PostgreSQL (Railway)
> 작성일: 2026년 4월

---

## 테이블 구조 개요

```
users
  └─ subjects (1:N)
       ├─ curriculum_items (1:N)
       ├─ stages (1:N)
       │    └─ stage_curriculum_items (N:M ← curriculum_items)
       └─ personas (1:1)
            ├─ persona_memory (1:N)
            ├─ teaching_sessions (1:N)
            │    └─ curriculum_items (FK, nullable)
            ├─ exams (1:N)
            │    └─ stages (FK)
            └─ weak_point_tags (1:N)
```

---

## DDL (전체 스키마)

```sql
-- ============================================================
-- 1. 사용자 계정
-- ============================================================
CREATE TABLE users (
  id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  email         TEXT        UNIQUE NOT NULL,
  password_hash TEXT        NOT NULL,
  created_at    TIMESTAMP   NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 2. 과목 (사용자가 직접 생성)
-- ============================================================
CREATE TABLE subjects (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name        TEXT        NOT NULL,           -- 예) "웹 기초"
  description TEXT,                           -- 예) "HTML·CSS·JS로 웹 만들기"
  created_at  TIMESTAMP   NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 3. 커리큘럼 항목 (과목 내 학습 주제 목록)
-- ============================================================
CREATE TABLE curriculum_items (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  subject_id  UUID        NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  title       TEXT        NOT NULL,           -- 예) "CSS 박스 모델"
  note        TEXT,                           -- 선택적 메모
  order_index INT         NOT NULL DEFAULT 0, -- 항목 표시 순서
  created_at  TIMESTAMP   NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 4. 단계 (커리큘럼 항목들을 묶은 챕터)
-- ============================================================
CREATE TABLE stages (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  subject_id  UUID        NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  name        TEXT        NOT NULL,           -- 예) "웹 초보", "웹 중수"
  order_index INT         NOT NULL DEFAULT 0, -- 단계 진행 순서
  passed      BOOLEAN     NOT NULL DEFAULT FALSE,
  passed_at   TIMESTAMP,                      -- 단계 통과 시각
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
  id               UUID  PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          UUID  NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  subject_id       UUID  NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  name             TEXT  NOT NULL,   -- 예) "제이"
  personality      TEXT  NOT NULL
                         CHECK (personality IN ('curious','careful','clumsy','perfectionist')),
  --  curious      : 망각 ×1.0 / 질문 3~4회 / 진급 75점
  --  careful      : 망각 ×0.7 / 질문 1~2회 / 진급 70점
  --  clumsy       : 망각 ×1.5 / 질문 2~3회 / 진급 80점
  --  perfectionist: 망각 ×0.8 / 질문 3~4회(심화) / 진급 85점
  current_stage_id UUID  REFERENCES stages(id),   -- 현재 진행 중인 단계
  created_at       TIMESTAMP NOT NULL DEFAULT NOW(),
  UNIQUE (subject_id)   -- 과목당 페르소나 1개
);

-- ============================================================
-- 7. 페르소나 지식 메모리 (에빙하우스 망각 곡선 적용)
-- ============================================================
-- 기억률은 저장하지 않고 API 요청 시마다 서버에서 실시간 계산:
--   retention(t) = exp(-t / stability)
--   t        : (NOW - last_taught_at) in days
--   stability: taught_count 에 따라 결정 (1 → 1.0, 2 → 2.0, 3 → 4.0, 4+ → 8.0)
--   personality_modifier: clumsy ×1.5, careful ×0.7, perfectionist ×0.8, curious ×1.0
-- --------------------------------------------------------
CREATE TABLE persona_memory (
  id             UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
  persona_id     UUID      NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
  curriculum_item_id UUID  REFERENCES curriculum_items(id),  -- NULL 허용 (자유 입력 개념)
  concept        TEXT      NOT NULL,    -- 학습한 개념명 (커리큘럼 항목 제목 또는 자유 입력)
  summary        TEXT,                  -- Claude가 생성한 한 줄 개념 요약
  taught_count   INT       NOT NULL DEFAULT 1,   -- 누적 수업(복습) 횟수
  stability      FLOAT     NOT NULL DEFAULT 1.0, -- 에빙하우스 안정성 계수 S
  last_taught_at TIMESTAMP NOT NULL DEFAULT NOW(),
  created_at     TIMESTAMP NOT NULL DEFAULT NOW(),
  UNIQUE (persona_id, concept)
);

-- ============================================================
-- 8. 수업 세션
-- ============================================================
-- 세션 종료 시:
--   1) messages 전체 → Claude Haiku로 concepts JSON 요약 → persona_memory 업데이트
--   2) Claude Haiku로 품질 평가 → quality_score, weak_points 저장
--   3) messages는 빈 배열로 초기화 (토큰 폭발 방지)
-- --------------------------------------------------------
CREATE TABLE teaching_sessions (
  id                 UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
  persona_id         UUID      NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
  curriculum_item_id UUID      REFERENCES curriculum_items(id),  -- NULL 허용 (자유 입력)
  concept            TEXT      NOT NULL,   -- 오늘 가르친 개념명
  quality_score      SMALLINT  CHECK (quality_score BETWEEN 0 AND 100),
  -- 평가 4항목: 정확성·깊이·예시·완결성 (각 25점)
  weak_points        JSONB     NOT NULL DEFAULT '[]',
  -- [{ "concept": "box-sizing", "description": "틀린 이해 표현 그대로" }]
  messages           JSONB     NOT NULL DEFAULT '[]',
  -- [{ "role": "user"|"assistant", "content": "...", "timestamp": "ISO8601" }]
  -- 세션 종료 후 요약 완료 시 [] 로 초기화
  summary_generated  BOOLEAN   NOT NULL DEFAULT FALSE,  -- 요약 완료 여부
  created_at         TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 9. 단계 시험
-- ============================================================
-- 채점 공식:
--   combined_score = (user_score × 0.6) + (persona_score × 0.4)
-- 진급 조건 (personality 별 기준):
--   curious      : combined ≥ 75 AND user ≥ 50 AND persona ≥ 30
--   careful      : combined ≥ 70 AND user ≥ 50 AND persona ≥ 30
--   clumsy       : combined ≥ 80 AND user ≥ 50 AND persona ≥ 30
--   perfectionist: combined ≥ 85 AND user ≥ 50 AND persona ≥ 30
-- --------------------------------------------------------
CREATE TABLE exams (
  id              UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
  persona_id      UUID      NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
  stage_id        UUID      NOT NULL REFERENCES stages(id),
  questions       JSONB     NOT NULL,
  -- [{
  --   "id": "q1",
  --   "type": "multiple_choice" | "short_answer",
  --   "content": "문제 내용",
  --   "options": ["①","②","③","④","⑤"] | null,
  --   "answer": "정답",
  --   "concept_tag": "관련 개념명",
  --   "difficulty": 1 | 2 | 3
  -- }]
  user_answers    JSONB     NOT NULL DEFAULT '[]',
  -- [{ "question_id": "q1", "answer": "사용자 답변" }]
  persona_answers JSONB     NOT NULL DEFAULT '[]',
  -- [{ "question_id": "q1", "thought": "생각 텍스트", "answer": "페르소나 답변" }]
  user_score      SMALLINT  CHECK (user_score BETWEEN 0 AND 100),
  persona_score   SMALLINT  CHECK (persona_score BETWEEN 0 AND 100),
  combined_score  SMALLINT  CHECK (combined_score BETWEEN 0 AND 100),
  passed          BOOLEAN,
  created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 10. 약점 태그 누적 (반복 오답 개념)
-- ============================================================
CREATE TABLE weak_point_tags (
  id             UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
  persona_id     UUID      NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
  concept        TEXT      NOT NULL,   -- 오답이 발생한 개념명
  fail_count     INT       NOT NULL DEFAULT 1,  -- 누적 오답 횟수
  last_failed_at TIMESTAMP NOT NULL DEFAULT NOW(),
  created_at     TIMESTAMP NOT NULL DEFAULT NOW(),
  UNIQUE (persona_id, concept)
);
```

---

## 인덱스

```sql
-- subjects
CREATE INDEX idx_subjects_user        ON subjects(user_id);

-- curriculum_items
CREATE INDEX idx_curriculum_subject   ON curriculum_items(subject_id, order_index);

-- stages
CREATE INDEX idx_stages_subject       ON stages(subject_id, order_index);

-- stage_curriculum_items
CREATE INDEX idx_sci_curriculum_item  ON stage_curriculum_items(curriculum_item_id);

-- personas
CREATE INDEX idx_personas_user        ON personas(user_id);

-- persona_memory
CREATE INDEX idx_memory_persona       ON persona_memory(persona_id);
CREATE INDEX idx_memory_last_taught   ON persona_memory(persona_id, last_taught_at);

-- teaching_sessions
CREATE INDEX idx_sessions_persona     ON teaching_sessions(persona_id, created_at DESC);
CREATE INDEX idx_sessions_item        ON teaching_sessions(curriculum_item_id);

-- exams
CREATE INDEX idx_exams_persona        ON exams(persona_id, created_at DESC);
CREATE INDEX idx_exams_stage          ON exams(stage_id);

-- weak_point_tags
CREATE INDEX idx_weak_tags_persona    ON weak_point_tags(persona_id, fail_count DESC);
```

---

## 주요 설계 결정 사항

### 1. 기억률(retention)은 컬럼으로 저장하지 않는다

```
기억률은 항상 서버에서 실시간 계산한다.
  retention = exp(-t / (stability × personality_modifier))

저장 값: stability (Float), last_taught_at (Timestamp)
계산 값: t = (NOW - last_taught_at).days → retention (0.0~1.0)

personality_modifier:
  curious       → 1.0
  careful       → 0.7  (느리게 잊음)
  clumsy        → 1.5  (빠르게 잊음)
  perfectionist → 0.8
```

### 2. 세션 메시지 초기화 (토큰 폭발 방지)

```
세션 종료 시:
  ① teaching_sessions.messages 전체 → Claude Haiku 요약 요청
  ② 결과 concepts[] → persona_memory (concept, summary) upsert
  ③ teaching_sessions.messages = []  ← 원본 삭제
  ④ teaching_sessions.summary_generated = TRUE

시험 생성 시 사용 데이터:
  persona_memory.summary 필드만 묶어서 전달
  → 수백 회 수업 후에도 토큰 양이 선형 증가하지 않음
```

### 3. 시험 해금 조건 — 단계 내 전체 항목 학습 완료

```
[시험 버튼 활성화 쿼리]

-- 현재 단계의 전체 항목 수
SELECT COUNT(*) FROM stage_curriculum_items WHERE stage_id = :stage_id;

-- 해당 항목 중 가르치기 세션이 1회 이상 존재하는 항목 수
SELECT COUNT(DISTINCT ts.curriculum_item_id)
FROM teaching_sessions ts
JOIN stage_curriculum_items sci ON sci.curriculum_item_id = ts.curriculum_item_id
WHERE sci.stage_id = :stage_id
  AND ts.persona_id = :persona_id;

-- 두 값이 일치할 때만 버튼 활성화
```

하나라도 미학습 항목이 있으면 시험 버튼은 비활성화되고
"아직 가르치지 않은 항목이 N개 남았어요" 문구를 표시한다.

### 4. persona_memory — curriculum_item_id nullable

커리큘럼 항목 없이 자유 입력으로 가르친 개념도 메모리에 저장 가능하도록 `curriculum_item_id`는 NULL 허용. `concept` 텍스트와 `persona_id` 조합을 UNIQUE 제약으로 중복 방지.

### 5. teaching_sessions.curriculum_item_id nullable

홈 화면의 "자유 가르치기" 기능(커리큘럼 항목 미선택 세션)을 지원하기 위해 NULL 허용.
단, 자유 입력 세션은 시험 해금 조건(전체 항목 학습 완료) 판정에 포함되지 않는다.

### 6. JSONB 컬럼 사용처 요약

| 테이블 | 컬럼 | 이유 |
|--------|------|------|
| `teaching_sessions` | `messages` | 대화 히스토리 구조 (role/content/timestamp), 가변 길이 |
| `teaching_sessions` | `weak_points` | 세션별 약점 개념 목록, 구조가 단순해 별도 테이블 불필요 |
| `exams` | `questions` | 문제 배열 (type별 schema가 다름, 5문제 고정) |
| `exams` | `user_answers` | 사용자 답변 배열 |
| `exams` | `persona_answers` | 페르소나 답변 + thought 텍스트 배열 |

---

## 기억률 단계별 게임 표시 기준

| 기억률 | 게임 표시 | 색상 |
|:------:|:--------:|:----:|
| 80%+  | 선명 | 🟢 |
| 60~80% | 흐릿해지는 중 | 🟡 |
| 40~60% | 많이 흐릿함 | 🟠 |
| 20~40% | 거의 잊어버림 | 🔴 |
| ~20%  | 잊어버림 | ⚫ |

---

## 시험 오답 확률 (페르소나 응시 시 프롬프트 주입값)

| 기억률 | 오답 확률 |
|:------:|:--------:|
| 70%+  | 10% |
| 40~70% | 40% |
| ~40%  | 70% |

---

## 엔티티 관계 다이어그램 (텍스트)

```
users ──< subjects ──< curriculum_items
                  ──< stages ──< stage_curriculum_items >── curriculum_items
                  ──── personas ──< persona_memory
                                ──< teaching_sessions >── curriculum_items
                                ──< exams >── stages
                                ──< weak_point_tags
```

---

*참조: `proposal.md` §12, `main_logic.md` 전체, `AI_API_Architecture.md` §3*
