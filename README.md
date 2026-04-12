# Teach-U (티츄) — Backend

> **"가르치면서 내가 더 배운다. 내 제자가 성장하면, 나도 성장한다."**
>
> 바이브코딩 AI활용 차세대 교육 솔루션 공모전 출품작

---

## 1. 프로젝트 소개

**Teach-U (티츄)** 는 기존 AI 교육 앱의 방향을 완전히 역전한 모바일 학습 앱입니다.

```
기존 AI 교육앱:   AI  ────▶  사용자   (AI가 가르치고, 사용자는 수동적으로 학습)
Teach-U:       사용자 ────▶  AI 학생  (사용자가 가르치고, AI가 배우는 학생)
```

사용자는 자신이 오늘 배운 내용을 **AI 학생 페르소나**에게 직접 설명합니다. AI는 소크라테스 문답법으로 질문하며, 사용자 스스로 오개념과 논리 빈틈을 발견하게 합니다.

### 핵심 메커니즘

| 메커니즘 | 설명 | 교육학 근거 |
|---------|------|-----------|
| **역할 역전** | 사용자가 AI에게 개념을 설명 | 파인만 기법 (Feynman Technique) |
| **페르소나 책임감** | AI 학생을 성장시키는 감정적 유대 | 프로테제 효과 (Protégé Effect) |
| **망각 시뮬레이션** | AI 학생이 에빙하우스 곡선으로 기억을 잃어감 | 에빙하우스 망각 곡선 (1885) |
| **커리큘럼 자유** | 사용자가 과목·단계·항목을 직접 설계 | 자기결정이론 (SDT) |
| **합산 시험** | 사용자와 AI 학생이 같은 시험을 치름 | 협력 학습 |

### 차별화 포인트

- **어떤 과목이든 가능** — 수학, 웹개발, 역사, 외국어 등 사용자가 직접 과목 생성
- **AI가 실제로 배우고 잊음** — DB + 수학 공식으로 구현한 가짜 망각이 아닌 구조화된 기억 시뮬레이션
- **약점 개념 사물함** — 시험 오답이 자동으로 복습 큐에 쌓이고 Claude가 맞춤 문제 생성

---

## 2. 기술 스택

| 레이어 | 기술 | 버전 |
|--------|------|------|
| **웹 프레임워크** | FastAPI | 0.115.6 |
| **ORM** | SQLAlchemy (async) | 2.0.37 |
| **DB 마이그레이션** | Alembic | 1.14.1 |
| **데이터베이스** | PostgreSQL | (Railway) |
| **AI** | Claude API (Anthropic) | claude-sonnet-4-6 |
| **인증** | JWT (python-jose) + Google OAuth | — |
| **Rate Limiting** | Redis | — |
| **모니터링** | Sentry | 2.19.2 |
| **런타임** | Python | 3.11 |
| **배포** | Railway | — |

---

## 3. 시작하기

### 사전 요구사항

- Python 3.11+
- PostgreSQL (또는 Railway 연결)
- Redis (Rate Limiting용, 없으면 in-memory fallback 동작)
- Anthropic API Key

### 환경 변수 설정

```env
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/dbname
JWT_SECRET=your-strong-jwt-secret
JWT_ISSUER=my-jeja
JWT_AUDIENCE=my-jeja-client
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-6
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_OAUTH_REDIRECT_URI=https://your-backend.up.railway.app/api/v1/auth/google/callback
GOOGLE_APP_REDIRECT_DEFAULT=exp://your-expo-redirect
REDIS_URL=redis://localhost:6379
APP_ENV=dev
CORS_ALLOW_ORIGINS=http://localhost:8081,https://your-frontend.com
ALLOWED_HOSTS=localhost,your-backend.up.railway.app
```

### 로컬 실행

```bash
# 1. 의존성 설치
cd backend
pip install -r requirements.txt

# 2. DB 마이그레이션
alembic upgrade head

# 3. 서버 시작
uvicorn app.main:app --reload --port 8000
```

### API 헬스 체크

```bash
curl https://your-backend.up.railway.app/api/v1/health
# → {"status": "ok"}
```

### Railway 배포

```bash
railway login
railway up
```

환경 변수는 Railway 대시보드의 Variables 탭에서 설정합니다.

---

## 4. API 레퍼런스

> 전체 명세: [`docs/API_spec.md`](docs/API_spec.md)
>
> Base URL: `https://<railway-domain>/api/v1`
> 인증: `Authorization: Bearer <access_token>` (모든 엔드포인트)

### 주요 엔드포인트 요약

#### 인증 (Auth)

```
POST /auth/register          # 이메일 회원가입
POST /auth/login             # 로그인 → JWT 반환
GET  /auth/google/url        # Google OAuth URL 반환
POST /auth/google/code       # Google 인가 코드 교환 → JWT 반환
GET  /auth/me                # 내 정보 조회
```

#### 과목·커리큘럼·단계

```
GET  /subjects                                    # 과목 목록 (페르소나 포함)
POST /subjects                                    # 과목 생성
POST /subjects/{id}/curriculum                    # 커리큘럼 항목 추가
POST /subjects/{id}/stages                        # 단계 생성
```

#### 가르치기 세션 (SSE 스트리밍)

```
POST /subjects/{id}/persona/sessions              # 세션 시작
POST /subjects/{id}/persona/sessions/{sid}/chat   # 채팅 전송 (SSE 스트림 반환)
POST /subjects/{id}/persona/sessions/{sid}/end    # 세션 종료 + 자동 평가
```

```javascript
// SSE 수신 예시 (프론트엔드)
const res = await fetch('/api/v1/subjects/.../sessions/.../chat', {
  method: 'POST',
  headers: { Authorization: 'Bearer ...', 'Content-Type': 'application/json' },
  body: JSON.stringify({ message: 'HTML이란 웹 페이지의 뼈대를 만드는 언어야' }),
});
const reader = res.body.getReader();
// event: token / event: done 형식으로 수신
```

#### 시험

```
POST /exams                  # 시험 생성 (가르친 내용 기반 Claude 문제 생성)
POST /exams/{exam_id}/submit # 답안 제출 + 채점 + 진급 판정
```

#### 약점 복습 (개념 사물함)

```
GET  /subjects/{id}/persona/weak-points                           # 약점 태그 목록
POST /subjects/{id}/persona/weak-points/{tag_id}/practice         # Claude 복습 문제 생성
POST /subjects/{id}/persona/weak-points/{tag_id}/practice/submit  # 답변 제출 + 퍼지 채점
```

**복습 제출 예시:**

```json
// POST .../practice/submit
// Request
{ "problem": "HTML의 시맨틱 태그가 필요한 이유를 설명하시오.", "answer": "검색 엔진이 내용을 구조적으로 이해할 수 있어서요" }

// Response
{ "is_correct": true, "feedback": "핵심을 잘 잡았어요! 접근성 향상도 중요한 이유 중 하나예요." }
```

---

## 5. 프로젝트 구조

```
_vibeContest_Back/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 앱 팩토리 (미들웨어, 라우터 등록)
│   │   ├── config.py            # 환경 변수 (pydantic-settings)
│   │   ├── deps.py              # 공통 의존성 (JWT 검증, DB 세션)
│   │   ├── ai/
│   │   │   ├── client.py        # ClaudeClient (stream_text / complete_text)
│   │   │   └── prompts.py       # Claude 프롬프트 빌더 7종
│   │   ├── auth/                # Google OAuth + JWT 인증
│   │   ├── subjects/            # 과목·커리큘럼·단계·페르소나·가르치기 세션·약점 복습
│   │   ├── exam/                # 시험 생성·채점·진급 판정
│   │   ├── persona/             # 페르소나 CRUD
│   │   ├── dashboard/           # 진행 현황 집계
│   │   ├── common/
│   │   │   ├── audit.py         # 감사 로그
│   │   │   ├── rate_limit.py    # Redis Rate Limiter
│   │   │   ├── security.py      # 보안 헤더, RequestContext 미들웨어
│   │   │   └── weak_points.py   # 약점 태그 upsert 헬퍼
│   │   ├── db/
│   │   │   ├── models.py        # SQLAlchemy ORM 모델
│   │   │   └── session.py       # async DB 세션
│   │   └── engines/
│   │       └── forgetting_curve.py  # 에빙하우스 망각 곡선 계산
│   ├── migrations/              # Alembic 마이그레이션
│   └── requirements.txt
└── docs/
    ├── instruction.md           # AI 협업 운영 지침 (SSoT)
    ├── API_spec.md              # 전체 REST API 명세
    ├── AI_API_Architecture.md   # Claude 호출 설계 + 프롬프트 7종
    ├── main_logic.md            # 핵심 구현 로직 (기억률, 시험, 복습)
    ├── DB_Schema.md             # DB 스키마 설계
    ├── deployment_checklist.md  # Railway 배포 체크리스트
    ├── design_UXUI_plan.md      # UI/UX 설계
    ├── prompt_history.md        # 기획 단계 LLM 대화 기록
    └── proposal.md              # 공모전 기획 제안서
```

---

## 6. 심사기준에 따른 차별성 강조

### 기술적 완성도

| 항목 | 구현 내용 |
|------|---------|
| **SSE 스트리밍** | FastAPI `StreamingResponse` + async generator로 Claude 응답을 토큰 단위로 실시간 전달 |
| **멀티턴 대화** | DB JSONB에 messages 배열 저장, 최근 20개 히스토리로 Claude API 호출 (역할 교대 자동 병합) |
| **Claude 7종 프롬프트** | 소크라테스 채팅·시험 생성·품질 평가·요약·복습 문제·퍼지 채점 등 목적별 분리 설계 |
| **망각 곡선 엔진** | `retention = e^(-t/S)` 실시간 계산, stability는 복습/가르치기 횟수에 비례 증가 |
| **보안** | JWT issuer/audience 검증, 시험 answer_key 채점 후 즉시 폐기, Rate Limit, 보안 헤더 |
| **모델 티어링** | Sonnet(대화·시험) vs Haiku(평가·요약) — 비용 60~70% 절감 |

### AI 활용 능력 및 효율성

- **프롬프트 목적별 분리**: 7가지 Claude 호출이 각각 독립된 프롬프트 빌더 함수로 관리
- **퍼지 채점**: 정확한 표현이 아닌 "핵심 이해도"를 Claude가 평가 — 단순 문자열 비교 탈피
- **subject_name 동적 주입**: 특정 과목을 하드코딩하지 않고 사용자 정의 과목명 주입
- **Prompt Caching 준비**: 고정 텍스트에 `cache_control` 적용 구조 (비용 추가 절감 가능)

### 기획력 및 실무 접합성

- **교육학 3이론 기반 설계**: 파인만 기법 + 프로테제 효과 + 에빙하우스 망각 곡선
- **50인 가상 페르소나** 인터뷰 기반 페인포인트 도출 (`docs/proposal.md`)
- **커리큘럼 전권 이양**: "사용자가 교수이자 선생님" — 어떤 분야든 자신만의 학습 설계

### 창의성

- "AI가 가르친다" → **"사용자가 AI를 가르친다"** 라는 전례 없는 역전 구조
- 망각 곡선을 가진 AI 학생이 실제로 배우고 잊는 시뮬레이션
- 사용자·AI 학생이 **함께 같은 시험**을 치르는 합산 채점 메커니즘

---

## 7. 시스템 아키텍처 구조

```
┌─────────────────────────────────────────────────────────────────────┐
│                          클라이언트                                    │
│                   React Native (Expo) App                            │
│           iOS / Android / Web (expo-web-browser)                     │
└─────────────────────────┬───────────────────────────────────────────┘
                          │  HTTPS + JWT Bearer
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        FastAPI Backend                               │
│                   (Railway — Python 3.11)                            │
│                                                                      │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐              │
│  │  Auth 모듈   │  │  Subjects 모듈 │  │   Exam 모듈   │              │
│  │ Google OAuth │  │ 과목·커리큘럼  │  │ 생성·채점·진급  │              │
│  │ JWT 발급/검증 │  │ 단계·세션·복습 │  │ answer_key폐기 │              │
│  └─────────────┘  └──────────────┘  └───────────────┘              │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                      AI 서비스 레이어                           │   │
│  │  ClaudeClient.stream_text()  ←── SSE 스트리밍 (가르치기 채팅)   │   │
│  │  ClaudeClient.complete_text() ←── JSON 출력 (시험·평가·복습)    │   │
│  │                                                                │   │
│  │  Prompt 1: 소크라테스 채팅 (Sonnet)                             │   │
│  │  Prompt 2: 시험 문제 생성 (Sonnet)                              │   │
│  │  Prompt 3: AI 학생 응시 (Haiku / 현재 서버 로직)                 │   │
│  │  Prompt 4: 수업 품질 평가 (Haiku)                               │   │
│  │  Prompt 5: 세션 요약 생성 (Haiku)                               │   │
│  │  Prompt 6: 복습 문제 생성 (Sonnet)                              │   │
│  │  Prompt 7: 복습 답변 퍼지 채점 (Sonnet)                          │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────┐  ┌────────────────────────────────────────┐   │
│  │  공통 인프라       │  │       망각 곡선 엔진                      │   │
│  │ Rate Limit(Redis)│  │  retention = e^(-t / stability)         │   │
│  │ 감사 로그(audit)  │  │  stability ↑ 가르치기/복습 횟수에 비례     │   │
│  │ 보안 헤더         │  │                                        │   │
│  └──────────────────┘  └────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
            ┌──────────────┴──────────────┐
            ▼                             ▼
┌─────────────────────┐       ┌─────────────────────┐
│    PostgreSQL        │       │    Claude API        │
│    (Railway)         │       │   (Anthropic)        │
│                      │       │                      │
│ users                │       │  claude-sonnet-4-6   │
│ subjects             │       │  claude-haiku-4-5    │
│ curriculum_items     │       │                      │
│ stages               │       └─────────────────────┘
│ personas             │
│ persona_memory       │
│ teaching_sessions    │
│ exams                │
│ weak_point_tags      │
└─────────────────────┘
```

### 핵심 데이터 흐름

```
[가르치기 → 기억 저장]
  사용자 메시지
    → DB 저장 (flag_modified) → Claude SSE 스트리밍
    → 세션 종료 시 Claude Haiku: 요약 + 품질 평가
    → persona_memory 업데이트 (stability 증가)

[시험 → 진급]
  시험 요청
    → 가르친 개념 조회 → Claude Sonnet: 5문항 생성
    → 합산 채점 (user×0.6 + persona×0.4)
    → combined ≥ 70 → 진급 / 미만 → weak_point_tags 추가

[복습 → 약점 해소]
  복습 요청
    → Claude Sonnet: 문제·힌트·개념 설명 생성
    → 사용자 답변 → Claude Sonnet: 퍼지 채점
    → 정답: WeakPointTag 삭제 + stability += 0.2
```

---

## 8. 마무리

**Teach-U (티츄)** 는 단순한 AI 챗봇 교육 도구가 아닙니다.

"가르치는 것이 최고의 학습법"이라는 수십 년간 검증된 교육학 원리를 AI와 접목하여, 사용자가 자신의 학습을 주도적으로 설계하고 AI 학생을 성장시키면서 자신도 함께 성장하는 **새로운 형태의 교육 경험**을 제안합니다.

> **Frontend Repository**: [TEAM-PEENOO/Front-end](https://github.com/TEAM-PEENOO/Front-end)
> **Backend Repository**: [TEAM-PEENOO/Back-end](https://github.com/TEAM-PEENOO/Back-end)

---

*제작: 태훈 × Claude Sonnet 4.6 (바이브코딩)*
*공모전: 바이브코딩 AI활용 차세대 교육 솔루션*
