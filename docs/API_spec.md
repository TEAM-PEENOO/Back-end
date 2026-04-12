# API 명세서 — 나의 제자 (My Jeja)

> 백엔드: FastAPI (Python 3.11)
> 인증: JWT Bearer Token
> Base URL: `https://<railway-domain>/api/v1`
> 작성 기준: `DB_Schema.md` 전체 테이블

---

## 데모 연동 기준(현재 구현)

- Google 웹 로그인:
  - `GET /auth/google/url`
  - `POST /auth/google/code`
- 과목/커리큘럼/단계:
  - `POST /subjects`
  - `POST /subjects/{subject_id}/curriculum`
  - `POST /subjects/{subject_id}/stages`
- 수업 세션(백엔드 구현 기준):
  - `POST /teaching/sessions`
  - `POST /teaching/sessions/{session_id}/messages`
  - `POST /teaching/sessions/{session_id}/finish`
- 시험:
  - `POST /subjects/{subject_id}/stages/{stage_id}/exams`
  - `POST /exams/{exam_id}/submit`

> 아래 상세 명세 일부는 기획안 기준으로 남아 있으며, 데모 연결은 위 경로를 우선 사용한다.

---

## 공통 규칙

### 인증 헤더
모든 `/auth/register`, `/auth/login`을 제외한 엔드포인트는 아래 헤더 필수.

```
Authorization: Bearer <access_token>
```

### 공통 응답 형식

**성공**
```json
{ "data": { ... } }
```

**오류**
```json
{ "error": { "code": "ERROR_CODE", "message": "설명" } }
```

### 공통 오류 코드

| HTTP | code | 설명 |
|------|------|------|
| 400 | `VALIDATION_ERROR` | 요청 바디/쿼리 파라미터 오류 |
| 401 | `UNAUTHORIZED` | 토큰 없음 또는 만료 |
| 403 | `FORBIDDEN` | 다른 사용자의 리소스 접근 |
| 404 | `NOT_FOUND` | 리소스 없음 |
| 409 | `CONFLICT` | 중복 리소스 (이메일, 과목당 페르소나 등) |
| 422 | `EXAM_LOCKED` | 시험 해금 조건 미충족 |
| 500 | `INTERNAL_ERROR` | 서버 내부 오류 |

---

## 목차

1. [인증 (Auth)](#1-인증-auth)
2. [과목 (Subjects)](#2-과목-subjects)
3. [커리큘럼 항목 (Curriculum Items)](#3-커리큘럼-항목-curriculum-items)
4. [단계 (Stages)](#4-단계-stages)
5. [페르소나 (Personas)](#5-페르소나-personas)
6. [페르소나 메모리 (Persona Memory)](#6-페르소나-메모리-persona-memory)
7. [수업 세션 (Teaching Sessions)](#7-수업-세션-teaching-sessions)
8. [시험 (Exams)](#8-시험-exams)
9. [약점 태그 (Weak Point Tags)](#9-약점-태그-weak-point-tags)
10. [진행 현황 (Progress)](#10-진행-현황-progress)

---

## 1. 인증 (Auth)

### 1-1. 회원가입

```
POST /auth/register
```

**Request Body**
```json
{
  "email": "user@example.com",
  "password": "plaintext_password"
}
```

**Response `201`**
```json
{
  "data": {
    "user": {
      "id": "uuid",
      "email": "user@example.com",
      "created_at": "2026-04-09T00:00:00Z"
    },
    "access_token": "jwt_token"
  }
}
```

**오류**
- `409 CONFLICT` — 이미 가입된 이메일

---

### 1-2. 로그인

```
POST /auth/login
```

**Request Body**
```json
{
  "email": "user@example.com",
  "password": "plaintext_password"
}
```

**Response `200`**
```json
{
  "data": {
    "user": {
      "id": "uuid",
      "email": "user@example.com",
      "created_at": "2026-04-09T00:00:00Z"
    },
    "access_token": "jwt_token"
  }
}
```

**오류**
- `401 UNAUTHORIZED` — 이메일 또는 비밀번호 불일치

---

### 1-3. 내 정보 조회

```
GET /auth/me
```

**Response `200`**
```json
{
  "data": {
    "id": "uuid",
    "email": "user@example.com",
    "created_at": "2026-04-09T00:00:00Z"
  }
}
```

---

### 1-4. 회원 탈퇴

```
DELETE /auth/me
```

**Response `204`** — No Content

> 연관된 모든 데이터(subjects, personas 등) CASCADE 삭제

---

## 2. 과목 (Subjects)

### 2-1. 과목 목록 조회

```
GET /subjects
```

**Response `200`**
```json
{
  "data": [
    {
      "id": "uuid",
      "name": "웹 기초",
      "description": "HTML·CSS·JS로 웹 만들기",
      "created_at": "2026-04-09T00:00:00Z",
      "persona": {
        "id": "uuid",
        "name": "제이",
        "personality": "curious",
        "current_stage_id": "uuid"
      }
    }
  ]
}
```

> `persona` 필드는 과목에 페르소나가 설정된 경우에만 포함. 없으면 `null`.

---

### 2-2. 과목 단건 조회

```
GET /subjects/{subject_id}
```

**Response `200`**
```json
{
  "data": {
    "id": "uuid",
    "name": "웹 기초",
    "description": "HTML·CSS·JS로 웹 만들기",
    "created_at": "2026-04-09T00:00:00Z",
    "persona": {
      "id": "uuid",
      "name": "제이",
      "personality": "curious",
      "current_stage_id": "uuid"
    }
  }
}
```

---

### 2-3. 과목 생성

```
POST /subjects
```

**Request Body**
```json
{
  "name": "웹 기초",
  "description": "HTML·CSS·JS로 웹 만들기"
}
```

**Response `201`**
```json
{
  "data": {
    "id": "uuid",
    "name": "웹 기초",
    "description": "HTML·CSS·JS로 웹 만들기",
    "created_at": "2026-04-09T00:00:00Z"
  }
}
```

---

### 2-4. 과목 수정

```
PATCH /subjects/{subject_id}
```

**Request Body** — 변경할 필드만 포함
```json
{
  "name": "웹 기초 (수정)",
  "description": "새 설명"
}
```

**Response `200`**
```json
{
  "data": {
    "id": "uuid",
    "name": "웹 기초 (수정)",
    "description": "새 설명",
    "created_at": "2026-04-09T00:00:00Z"
  }
}
```

---

### 2-5. 과목 삭제

```
DELETE /subjects/{subject_id}
```

**Response `204`** — No Content

> 연관된 curriculum_items, stages, persona 등 CASCADE 삭제

---

## 3. 커리큘럼 항목 (Curriculum Items)

### 3-1. 커리큘럼 항목 목록 조회

```
GET /subjects/{subject_id}/curriculum
```

**Response `200`**
```json
{
  "data": [
    {
      "id": "uuid",
      "subject_id": "uuid",
      "title": "CSS 박스 모델",
      "note": "선택 메모",
      "order_index": 3,
      "created_at": "2026-04-09T00:00:00Z",
      "taught": true
    }
  ]
}
```

> `taught`: 이 항목에 대한 가르치기 세션이 1회 이상 존재하면 `true`

---

### 3-2. 커리큘럼 항목 단건 조회

```
GET /subjects/{subject_id}/curriculum/{item_id}
```

**Response `200`**
```json
{
  "data": {
    "id": "uuid",
    "subject_id": "uuid",
    "title": "CSS 박스 모델",
    "note": "선택 메모",
    "order_index": 3,
    "created_at": "2026-04-09T00:00:00Z",
    "taught": true
  }
}
```

---

### 3-3. 커리큘럼 항목 추가

```
POST /subjects/{subject_id}/curriculum
```

**Request Body**
```json
{
  "title": "CSS 박스 모델",
  "note": "선택 메모",
  "order_index": 3
}
```

> `order_index` 생략 시 현재 목록 마지막에 추가

**Response `201`**
```json
{
  "data": {
    "id": "uuid",
    "subject_id": "uuid",
    "title": "CSS 박스 모델",
    "note": "선택 메모",
    "order_index": 3,
    "created_at": "2026-04-09T00:00:00Z"
  }
}
```

---

### 3-4. 커리큘럼 항목 수정

```
PATCH /subjects/{subject_id}/curriculum/{item_id}
```

**Request Body** — 변경할 필드만 포함
```json
{
  "title": "CSS 박스 모델 (수정)",
  "note": "수정된 메모"
}
```

**Response `200`**
```json
{
  "data": {
    "id": "uuid",
    "title": "CSS 박스 모델 (수정)",
    "note": "수정된 메모",
    "order_index": 3,
    "created_at": "2026-04-09T00:00:00Z"
  }
}
```

---

### 3-5. 커리큘럼 항목 순서 일괄 변경

```
PUT /subjects/{subject_id}/curriculum/reorder
```

**Request Body**
```json
{
  "order": ["uuid_item3", "uuid_item1", "uuid_item2"]
}
```

> `order` 배열의 인덱스 순서대로 `order_index` 재할당

**Response `200`**
```json
{
  "data": [
    { "id": "uuid_item3", "order_index": 0 },
    { "id": "uuid_item1", "order_index": 1 },
    { "id": "uuid_item2", "order_index": 2 }
  ]
}
```

---

### 3-6. 커리큘럼 항목 삭제

```
DELETE /subjects/{subject_id}/curriculum/{item_id}
```

**Response `204`** — No Content

---

## 4. 단계 (Stages)

### 4-1. 단계 목록 조회

```
GET /subjects/{subject_id}/stages
```

**Response `200`**
```json
{
  "data": [
    {
      "id": "uuid",
      "subject_id": "uuid",
      "name": "웹 초보",
      "order_index": 0,
      "passed": false,
      "passed_at": null,
      "created_at": "2026-04-09T00:00:00Z",
      "curriculum_items": [
        {
          "id": "uuid",
          "title": "HTML 기본 구조 이해",
          "order_index": 0,
          "taught": true
        }
      ],
      "exam_unlocked": false,
      "untaught_count": 2
    }
  ]
}
```

> - `exam_unlocked`: 단계 내 전체 항목 학습 완료 시 `true`
> - `untaught_count`: 미학습 항목 수 (해금 조건 미충족 시 UI 표시용)

---

### 4-2. 단계 단건 조회

```
GET /subjects/{subject_id}/stages/{stage_id}
```

**Response `200`**
```json
{
  "data": {
    "id": "uuid",
    "subject_id": "uuid",
    "name": "웹 초보",
    "order_index": 0,
    "passed": false,
    "passed_at": null,
    "created_at": "2026-04-09T00:00:00Z",
    "curriculum_items": [ ... ],
    "exam_unlocked": false,
    "untaught_count": 2
  }
}
```

---

### 4-3. 단계 생성

```
POST /subjects/{subject_id}/stages
```

**Request Body**
```json
{
  "name": "웹 초보",
  "order_index": 0,
  "curriculum_item_ids": ["uuid1", "uuid2", "uuid3", "uuid4"]
}
```

> `order_index` 생략 시 마지막에 추가
> `curriculum_item_ids` 생략 시 빈 단계로 생성 가능

**Response `201`**
```json
{
  "data": {
    "id": "uuid",
    "name": "웹 초보",
    "order_index": 0,
    "passed": false,
    "passed_at": null,
    "created_at": "2026-04-09T00:00:00Z",
    "curriculum_items": [ ... ]
  }
}
```

---

### 4-4. 단계 수정

```
PATCH /subjects/{subject_id}/stages/{stage_id}
```

> 이미 통과한 단계(`passed: true`)는 수정 불가 → `403 FORBIDDEN`

**Request Body** — 변경할 필드만 포함
```json
{
  "name": "웹 입문",
  "curriculum_item_ids": ["uuid1", "uuid2"]
}
```

**Response `200`**
```json
{
  "data": {
    "id": "uuid",
    "name": "웹 입문",
    "order_index": 0,
    "curriculum_items": [ ... ]
  }
}
```

**오류**
- `403 FORBIDDEN` — 이미 통과한 단계 수정 시도

---

### 4-5. 단계 삭제

```
DELETE /subjects/{subject_id}/stages/{stage_id}
```

> 이미 통과한 단계는 삭제 불가 → `403 FORBIDDEN`

**Response `204`** — No Content

---

### 4-6. 단계 순서 일괄 변경

```
PUT /subjects/{subject_id}/stages/reorder
```

**Request Body**
```json
{
  "order": ["uuid_stage2", "uuid_stage1", "uuid_stage3"]
}
```

**Response `200`**
```json
{
  "data": [
    { "id": "uuid_stage2", "order_index": 0 },
    { "id": "uuid_stage1", "order_index": 1 },
    { "id": "uuid_stage3", "order_index": 2 }
  ]
}
```

---

## 5. 페르소나 (Personas)

### 5-1. 페르소나 조회

```
GET /subjects/{subject_id}/persona
```

**Response `200`**
```json
{
  "data": {
    "id": "uuid",
    "subject_id": "uuid",
    "name": "제이",
    "personality": "curious",
    "current_stage_id": "uuid",
    "created_at": "2026-04-09T00:00:00Z"
  }
}
```

**오류**
- `404 NOT_FOUND` — 아직 페르소나 미설정

---

### 5-2. 페르소나 생성

```
POST /subjects/{subject_id}/persona
```

> 과목당 페르소나 1개 제한. 이미 존재하면 `409 CONFLICT`.

**Request Body**
```json
{
  "name": "제이",
  "personality": "curious"
}
```

> `personality`: `"curious"` | `"careful"` | `"clumsy"` | `"perfectionist"`

**Response `201`**
```json
{
  "data": {
    "id": "uuid",
    "subject_id": "uuid",
    "name": "제이",
    "personality": "curious",
    "current_stage_id": null,
    "created_at": "2026-04-09T00:00:00Z"
  }
}
```

---

### 5-3. 페르소나 수정

```
PATCH /subjects/{subject_id}/persona
```

**Request Body** — 변경할 필드만 포함
```json
{
  "name": "제이나",
  "personality": "careful"
}
```

**Response `200`**
```json
{
  "data": {
    "id": "uuid",
    "name": "제이나",
    "personality": "careful",
    "current_stage_id": "uuid"
  }
}
```

---

### 5-4. 페르소나 삭제

```
DELETE /subjects/{subject_id}/persona
```

**Response `204`** — No Content

> persona_memory, teaching_sessions, exams, weak_point_tags CASCADE 삭제

---

## 6. 페르소나 메모리 (Persona Memory)

### 6-1. 메모리 목록 조회 (기억률 포함)

```
GET /subjects/{subject_id}/persona/memory
```

> 기억률은 서버에서 실시간 계산하여 응답에 포함.

**Response `200`**
```json
{
  "data": [
    {
      "id": "uuid",
      "concept": "CSS 박스 모델",
      "summary": "content/padding/border/margin 4층 구조. 배경색은 padding까지 적용됨.",
      "taught_count": 2,
      "stability": 2.0,
      "last_taught_at": "2026-04-06T10:00:00Z",
      "retention": 0.78,
      "retention_label": "흐릿해지는 중",
      "curriculum_item_id": "uuid"
    }
  ]
}
```

> `retention_label` 값:
> - `"선명"` (≥0.8)
> - `"흐릿해지는 중"` (0.6~0.8)
> - `"많이 흐릿함"` (0.4~0.6)
> - `"거의 잊어버림"` (0.2~0.4)
> - `"잊어버림"` (<0.2)

---

### 6-2. 메모리 단건 조회

```
GET /subjects/{subject_id}/persona/memory/{memory_id}
```

**Response `200`**
```json
{
  "data": {
    "id": "uuid",
    "concept": "CSS 박스 모델",
    "summary": "...",
    "taught_count": 2,
    "stability": 2.0,
    "last_taught_at": "2026-04-06T10:00:00Z",
    "retention": 0.78,
    "retention_label": "흐릿해지는 중",
    "curriculum_item_id": "uuid"
  }
}
```

---

### 6-3. 메모리 수동 삭제

```
DELETE /subjects/{subject_id}/persona/memory/{memory_id}
```

**Response `204`** — No Content

> 일반적으로 세션 종료 시 자동 생성/갱신되지만, 잘못 생성된 항목 삭제용.

---

## 7. 수업 세션 (Teaching Sessions)

### 7-1. 세션 목록 조회

```
GET /subjects/{subject_id}/persona/sessions
```

**Query Params**

| 파라미터 | 타입 | 설명 |
|---------|------|------|
| `curriculum_item_id` | uuid (optional) | 특정 항목 세션만 필터 |
| `limit` | int (optional, default 20) | 최대 반환 수 |
| `offset` | int (optional, default 0) | 페이지네이션 오프셋 |

**Response `200`**
```json
{
  "data": [
    {
      "id": "uuid",
      "persona_id": "uuid",
      "curriculum_item_id": "uuid",
      "concept": "CSS 박스 모델",
      "quality_score": 88,
      "weak_points": [
        { "concept": "box-sizing", "description": "border가 width 안에 포함된다고 오해함" }
      ],
      "summary_generated": true,
      "created_at": "2026-04-09T10:00:00Z"
    }
  ],
  "total": 12
}
```

> `messages` 필드는 목록 조회에서 제외 (세션 단건 조회 시만 포함).

---

### 7-2. 세션 단건 조회

```
GET /subjects/{subject_id}/persona/sessions/{session_id}
```

**Response `200`**
```json
{
  "data": {
    "id": "uuid",
    "persona_id": "uuid",
    "curriculum_item_id": "uuid",
    "concept": "CSS 박스 모델",
    "quality_score": 88,
    "weak_points": [ ... ],
    "messages": [
      { "role": "user", "content": "CSS 박스 모델은 ...", "timestamp": "2026-04-09T10:00:00Z" },
      { "role": "assistant", "content": "아, 그럼 padding이랑 ...", "timestamp": "2026-04-09T10:00:05Z" }
    ],
    "summary_generated": true,
    "created_at": "2026-04-09T10:00:00Z"
  }
}
```

---

### 7-3. 세션 시작 (생성)

```
POST /subjects/{subject_id}/persona/sessions
```

**Request Body**
```json
{
  "curriculum_item_id": "uuid",
  "concept": "CSS 박스 모델"
}
```

> `curriculum_item_id`는 생략 가능 (자유 가르치기). 생략 시 `concept`만 필수.

**Response `201`**
```json
{
  "data": {
    "id": "uuid",
    "persona_id": "uuid",
    "curriculum_item_id": "uuid",
    "concept": "CSS 박스 모델",
    "quality_score": null,
    "weak_points": [],
    "messages": [],
    "summary_generated": false,
    "created_at": "2026-04-09T10:00:00Z"
  }
}
```

---

### 7-4. 채팅 메시지 전송 (소크라테스 AI 응답 스트리밍)

```
POST /subjects/{subject_id}/persona/sessions/{session_id}/chat
```

> **Server-Sent Events(SSE)** 스트리밍 응답.
> Claude Sonnet 호출 → 페르소나 응답 스트림.

**Request Body**
```json
{
  "message": "CSS 박스 모델은 content, padding, border, margin으로 구성돼"
}
```

**Response `200` — SSE Stream**
```
Content-Type: text/event-stream

data: {"delta": "아, 그럼 "}
data: {"delta": "padding이랑 margin은 "}
data: {"delta": "뭐가 다른 건가요?"}
data: {"done": true}
```

> 세션 DB의 `messages`에 user/assistant 메시지가 자동 추가됨.

---

### 7-5. 세션 종료

```
POST /subjects/{subject_id}/persona/sessions/{session_id}/end
```

> 세션 종료 처리:
> 1. Claude Haiku로 개념 요약 생성 → `persona_memory` upsert
> 2. Claude Haiku로 수업 품질 평가 → `quality_score`, `weak_points` 저장
> 3. `teaching_sessions.messages = []` (토큰 폭발 방지)
> 4. `summary_generated = true`

**Request Body** — 없음

**Response `200`**
```json
{
  "data": {
    "session_id": "uuid",
    "quality_score": 88,
    "weak_points": [
      { "concept": "box-sizing", "description": "border가 width 안에 포함된다고 오해함" }
    ],
    "updated_memories": [
      {
        "concept": "CSS 박스 모델",
        "summary": "content/padding/border/margin 4층 구조.",
        "taught_count": 2,
        "retention": 0.95
      }
    ]
  }
}
```

---

### 7-6. 세션 삭제

```
DELETE /subjects/{subject_id}/persona/sessions/{session_id}
```

**Response `204`** — No Content

---

## 8. 시험 (Exams)

### 8-1. 시험 목록 조회

```
GET /subjects/{subject_id}/persona/exams
```

**Query Params**

| 파라미터 | 타입 | 설명 |
|---------|------|------|
| `stage_id` | uuid (optional) | 특정 단계 시험만 필터 |

**Response `200`**
```json
{
  "data": [
    {
      "id": "uuid",
      "stage_id": "uuid",
      "stage_name": "웹 초보",
      "user_score": 85,
      "persona_score": 60,
      "combined_score": 75,
      "passed": true,
      "created_at": "2026-04-09T12:00:00Z"
    }
  ]
}
```

---

### 8-2. 시험 단건 조회

```
GET /subjects/{subject_id}/persona/exams/{exam_id}
```

**Response `200`**
```json
{
  "data": {
    "id": "uuid",
    "stage_id": "uuid",
    "questions": [
      {
        "id": "q1",
        "type": "multiple_choice",
        "content": "CSS 박스 모델에서 배경색이 적용되는 영역은?",
        "options": ["① content만", "② content + padding", "③ content + padding + border", "④ 전체", "⑤ padding만"],
        "answer": "② content + padding",
        "concept_tag": "CSS 박스 모델",
        "difficulty": 1
      }
    ],
    "user_answers": [
      { "question_id": "q1", "answer": "② content + padding" }
    ],
    "persona_answers": [
      { "question_id": "q1", "thought": "배경색은... padding까지였나요?", "answer": "② content + padding" }
    ],
    "user_score": 85,
    "persona_score": 60,
    "combined_score": 75,
    "passed": true,
    "created_at": "2026-04-09T12:00:00Z"
  }
}
```

---

### 8-3. 시험 생성 (단계 시험 요청)

```
POST /subjects/{subject_id}/stages/{stage_id}/exams
```

> **해금 조건 확인**: 단계 내 전체 커리큘럼 항목에 세션이 없으면 `422 EXAM_LOCKED`.
> 이미 생성된 미완료 시험이 있으면 새로 생성하지 않고 기존 시험 반환.

**Request Body** — 없음

**Response `201`**
```json
{
  "data": {
    "id": "uuid",
    "stage_id": "uuid",
    "questions": [
      {
        "id": "q1",
        "type": "multiple_choice",
        "content": "문제 내용",
        "options": ["① ...", "② ...", "③ ...", "④ ...", "⑤ ..."],
        "concept_tag": "CSS 박스 모델",
        "difficulty": 1
      }
    ],
    "user_answers": [],
    "persona_answers": [],
    "user_score": null,
    "persona_score": null,
    "combined_score": null,
    "passed": null,
    "created_at": "2026-04-09T12:00:00Z"
  }
}
```

> `answer` 필드는 사용자 응시 중에는 응답에서 제외됨 (채점 후 공개).

**오류**
- `422 EXAM_LOCKED` — 미학습 항목이 남아있는 경우
  ```json
  {
    "error": {
      "code": "EXAM_LOCKED",
      "message": "아직 가르치지 않은 항목이 2개 남았어요.",
      "untaught_items": [
        { "id": "uuid", "title": "CSS 박스 모델" },
        { "id": "uuid", "title": "Flexbox 레이아웃" }
      ]
    }
  }
  ```

---

### 8-4. 사용자 답변 제출

```
PUT /subjects/{subject_id}/persona/exams/{exam_id}/user-answers
```

**Request Body**
```json
{
  "answers": [
    { "question_id": "q1", "answer": "② content + padding" },
    { "question_id": "q2", "answer": "border-box" },
    { "question_id": "q3", "answer": "① display: flex" },
    { "question_id": "q4", "answer": "justify-content" },
    { "question_id": "q5", "answer": "④ margin은 border 밖의 공간" }
  ]
}
```

**Response `200`**
```json
{
  "data": {
    "exam_id": "uuid",
    "user_answers_saved": true
  }
}
```

---

### 8-5. 시험 채점 및 결과 확정

```
POST /subjects/{subject_id}/persona/exams/{exam_id}/grade
```

> **처리 순서**:
> 1. 기억률 기반 오답 확률 계산
> 2. Claude Haiku: 페르소나 답변 생성
> 3. 사용자/페르소나 점수 채점
> 4. `combined_score = user_score × 0.6 + persona_score × 0.4`
> 5. 진급 판정 (personality별 기준 적용)
> 6. 통과 시: `stages.passed = true`, `personas.current_stage_id` 업데이트
> 7. 오답 개념 → `weak_point_tags` upsert

**Request Body** — 없음

**Response `200`**
```json
{
  "data": {
    "exam_id": "uuid",
    "user_score": 85,
    "persona_score": 60,
    "combined_score": 75,
    "passed": true,
    "pass_threshold": 75,
    "persona_answers": [
      {
        "question_id": "q1",
        "thought": "배경색은... padding까지였나요?",
        "answer": "② content + padding"
      }
    ],
    "wrong_concepts": ["box-sizing", "CSS 우선순위"],
    "next_stage_id": "uuid"
  }
}
```

---

### 8-6. 시험 삭제

```
DELETE /subjects/{subject_id}/persona/exams/{exam_id}
```

> 미완료 시험(`passed: null`)만 삭제 가능. 완료된 시험은 삭제 불가 → `403 FORBIDDEN`.

**Response `204`** — No Content

---

## 9. 약점 태그 (Weak Point Tags)

### 9-1. 약점 태그 목록 조회

```
GET /subjects/{subject_id}/persona/weak-points
```

**Response `200`**
```json
{
  "data": [
    {
      "id": "uuid",
      "concept": "box-sizing",
      "fail_count": 2,
      "last_failed_at": "2026-04-09T12:00:00Z",
      "created_at": "2026-04-08T12:00:00Z"
    }
  ]
}
```

> `fail_count` 내림차순 정렬

---

### 9-2. 약점 태그 단건 조회

```
GET /subjects/{subject_id}/persona/weak-points/{tag_id}
```

**Response `200`**
```json
{
  "data": {
    "id": "uuid",
    "concept": "box-sizing",
    "fail_count": 2,
    "last_failed_at": "2026-04-09T12:00:00Z",
    "created_at": "2026-04-08T12:00:00Z"
  }
}
```

---

### 9-3. 약점 태그 수동 삭제

```
DELETE /subjects/{subject_id}/persona/weak-points/{tag_id}
```

**Response `204`** — No Content

> 정상적으로는 시험 채점 시 자동 생성/갱신. 해소됐다고 판단 시 수동 삭제 가능.

---

### 9-4. 약점 개념 복습 콘텐츠 생성

```
POST /subjects/{subject_id}/persona/weak-points/{tag_id}/practice
```

> Claude AI가 해당 과목·개념에 맞는 복습 문제, 단계별 힌트, 핵심 개념 설명을 생성하여 반환한다.  
> PracticeScreen("개념 사물함 → 복습하기")에서 호출됨.

**Response `200`**
```json
{
  "data": {
    "concept": "진지한 여가",
    "fail_count": 2,
    "problem": "여가 활동이 '진지한 여가'로 발전했을 때 나타날 수 있는 사회적 이점을 두 가지 서술하시오.",
    "hints": [
      "개인의 취미가 전문성으로 이어지는 과정을 생각해봐요",
      "그 활동이 다른 사람들과 어떤 관계를 만드는지 떠올려봐요",
      "경제적·사회적 기여 측면에서도 생각해봐요"
    ],
    "concept_title": "진지한 여가 핵심 정리",
    "concept_explanation": "진지한 여가란 단순 휴식이 아닌 꾸준한 노력과 기술 습득을 동반하는 여가 활동이에요.\n취미가 전문성으로 발전하면 원데이 클래스, 커뮤니티 형성 등 사회적 가치를 창출할 수 있어요."
  }
}
```

**Error `404`** — Weak point tag not found

---

### 9-5. 복습 답변 제출 및 채점

```
POST /subjects/{subject_id}/persona/weak-points/{tag_id}/practice/submit
```

> 사용자가 복습 문제에 대한 답변을 제출하면 Claude AI가 퍼지 채점을 수행한다.  
> 완벽한 표현이 아니어도 핵심 내용을 파악했으면 정답으로 인정한다.  
> 정답 시: `WeakPointTag` 삭제 + `PersonaMemory.stability += 0.2` (기억 유지율 증가).

**Request Body**
```json
{
  "problem": "여가 활동이 '진지한 여가'로 발전했을 때 나타날 수 있는 사회적 이점을 두 가지 서술하시오.",
  "answer": "전문성이 높아지고 커뮤니티 형성에 기여할 수 있다."
}
```

**Response `200`**
```json
{
  "is_correct": true,
  "feedback": "핵심을 잘 파악했어요! 전문성과 커뮤니티 측면을 모두 짚었네요."
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `is_correct` | boolean | 핵심 이해 여부 (퍼지 채점) |
| `feedback` | string | 친근한 톤의 1~2문장 피드백 |

**정답(`is_correct=true`) 시 서버 동작**:
1. `WeakPointTag` 삭제 → 개념 사물함에서 제거
2. `PersonaMemory.stability = min(1.0, stability + 0.2)` → 기억 유지율 강화

**Error `404`** — Weak point tag not found

---

## 10. 진행 현황 (Progress)

### 10-1. 과목 전체 진행 현황

```
GET /subjects/{subject_id}/progress
```

> 홈 화면의 제자 상태 카드, 단계 진행 현황, 이해도 그래프에 필요한 데이터를 한 번에 제공.

**Response `200`**
```json
{
  "data": {
    "subject": {
      "id": "uuid",
      "name": "웹 기초"
    },
    "persona": {
      "id": "uuid",
      "name": "제이",
      "personality": "curious"
    },
    "current_stage": {
      "id": "uuid",
      "name": "웹 초보",
      "order_index": 0,
      "exam_unlocked": false,
      "untaught_count": 1,
      "items": [
        {
          "id": "uuid",
          "title": "HTML 기본 구조 이해",
          "taught": true,
          "retention": 0.72,
          "retention_label": "흐릿해지는 중"
        }
      ]
    },
    "overall_retention": 0.72,
    "stage_history": [
      {
        "stage_id": "uuid",
        "stage_name": "웹 초보",
        "passed": false,
        "passed_at": null,
        "exam_scores": [
          {
            "exam_id": "uuid",
            "combined_score": 75,
            "passed": true,
            "created_at": "2026-04-09T12:00:00Z"
          }
        ]
      }
    ],
    "weak_points": [
      { "concept": "box-sizing", "fail_count": 2 }
    ]
  }
}
```

> `overall_retention`: 현재 단계 항목들의 기억률 평균

---

### 10-2. 단계별 시험 점수 이력

```
GET /subjects/{subject_id}/stages/{stage_id}/exam-history
```

> 이해도 그래프 (회차별 점수 변화 선 그래프) 데이터용.

**Response `200`**
```json
{
  "data": {
    "stage_id": "uuid",
    "stage_name": "웹 초보",
    "exams": [
      {
        "exam_id": "uuid",
        "attempt": 1,
        "user_score": 60,
        "persona_score": 45,
        "combined_score": 54,
        "passed": false,
        "created_at": "2026-04-07T12:00:00Z"
      },
      {
        "exam_id": "uuid",
        "attempt": 2,
        "user_score": 85,
        "persona_score": 60,
        "combined_score": 75,
        "passed": true,
        "created_at": "2026-04-09T12:00:00Z"
      }
    ]
  }
}
```

---

## 엔드포인트 전체 목록

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/auth/register` | 회원가입 |
| `POST` | `/auth/login` | 로그인 |
| `GET` | `/auth/me` | 내 정보 조회 |
| `DELETE` | `/auth/me` | 회원 탈퇴 |
| `GET` | `/subjects` | 과목 목록 |
| `GET` | `/subjects/{id}` | 과목 단건 조회 |
| `POST` | `/subjects` | 과목 생성 |
| `PATCH` | `/subjects/{id}` | 과목 수정 |
| `DELETE` | `/subjects/{id}` | 과목 삭제 |
| `GET` | `/subjects/{id}/curriculum` | 커리큘럼 항목 목록 |
| `GET` | `/subjects/{id}/curriculum/{item_id}` | 항목 단건 조회 |
| `POST` | `/subjects/{id}/curriculum` | 항목 추가 |
| `PATCH` | `/subjects/{id}/curriculum/{item_id}` | 항목 수정 |
| `PUT` | `/subjects/{id}/curriculum/reorder` | 항목 순서 변경 |
| `DELETE` | `/subjects/{id}/curriculum/{item_id}` | 항목 삭제 |
| `GET` | `/subjects/{id}/stages` | 단계 목록 |
| `GET` | `/subjects/{id}/stages/{stage_id}` | 단계 단건 조회 |
| `POST` | `/subjects/{id}/stages` | 단계 생성 |
| `PATCH` | `/subjects/{id}/stages/{stage_id}` | 단계 수정 |
| `PUT` | `/subjects/{id}/stages/reorder` | 단계 순서 변경 |
| `DELETE` | `/subjects/{id}/stages/{stage_id}` | 단계 삭제 |
| `GET` | `/subjects/{id}/persona` | 페르소나 조회 |
| `POST` | `/subjects/{id}/persona` | 페르소나 생성 |
| `PATCH` | `/subjects/{id}/persona` | 페르소나 수정 |
| `DELETE` | `/subjects/{id}/persona` | 페르소나 삭제 |
| `GET` | `/subjects/{id}/persona/memory` | 메모리 목록 (기억률 포함) |
| `GET` | `/subjects/{id}/persona/memory/{mem_id}` | 메모리 단건 조회 |
| `DELETE` | `/subjects/{id}/persona/memory/{mem_id}` | 메모리 삭제 |
| `GET` | `/subjects/{id}/persona/sessions` | 세션 목록 |
| `GET` | `/subjects/{id}/persona/sessions/{session_id}` | 세션 단건 조회 |
| `POST` | `/subjects/{id}/persona/sessions` | 세션 시작 |
| `POST` | `/subjects/{id}/persona/sessions/{session_id}/chat` | 채팅 전송 (SSE) |
| `POST` | `/subjects/{id}/persona/sessions/{session_id}/end` | 세션 종료 |
| `DELETE` | `/subjects/{id}/persona/sessions/{session_id}` | 세션 삭제 |
| `GET` | `/subjects/{id}/persona/exams` | 시험 목록 |
| `GET` | `/subjects/{id}/persona/exams/{exam_id}` | 시험 단건 조회 |
| `POST` | `/subjects/{id}/stages/{stage_id}/exams` | 시험 생성 (해금 검증) |
| `PUT` | `/subjects/{id}/persona/exams/{exam_id}/user-answers` | 사용자 답변 제출 |
| `POST` | `/subjects/{id}/persona/exams/{exam_id}/grade` | 채점 및 결과 확정 |
| `DELETE` | `/subjects/{id}/persona/exams/{exam_id}` | 시험 삭제 |
| `GET` | `/subjects/{id}/persona/weak-points` | 약점 태그 목록 |
| `GET` | `/subjects/{id}/persona/weak-points/{tag_id}` | 약점 태그 단건 조회 |
| `DELETE` | `/subjects/{id}/persona/weak-points/{tag_id}` | 약점 태그 삭제 |
| `POST` | `/subjects/{id}/persona/weak-points/{tag_id}/practice` | 약점 개념 복습 콘텐츠 생성 (AI) |
| `POST` | `/subjects/{id}/persona/weak-points/{tag_id}/practice/submit` | 복습 답변 제출 및 퍼지 채점 (AI) |
| `GET` | `/subjects/{id}/progress` | 과목 전체 진행 현황 |
| `GET` | `/subjects/{id}/stages/{stage_id}/exam-history` | 단계 시험 이력 |

---

*참조: `DB_Schema.md`, `proposal.md` §11~12, `AI_API_Architecture.md`*
