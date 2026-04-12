# 지침서 (Instruction Guide) — Teach-U (티츄)

> **이 문서는 모든 공유 문서의 Single Source of Truth(SSoT)입니다.**
> 공유 문서를 수정할 때는 반드시 **백엔드 레포에서 먼저 수정**하고, 이후 프론트엔드 레포로 동기화합니다.
>
> 동기화 명령 (백엔드 레포 루트에서):
> ```sh
> # 공유 문서 전체 동기화
> rsync -av docs/instruction.md ../vibeContest/docs/
> rsync -av docs/architecture/{main_logic,AI_API_Architecture,DB_Schema}.md ../vibeContest/docs/
> rsync -av docs/api/API_spec.md ../vibeContest/docs/
> rsync -av docs/planning/{prompt_history,proposal}.md ../vibeContest/docs/
> ```

---

## ⚠️ SECTION 0 — AI 협업 절대 규칙 (최고 우선순위)

**아래 규칙들은 모든 작업에서 예외 없이 준수한다.**

---

### 0-1. 문서 업데이트 의무 규칙 (엄격)

```
매 기능 업데이트마다 문서들에 대하여 업데이트를 해야 할 것이 있으면 무조건 진행할 것.

구체적 기준:
- 새 API 엔드포인트 추가          → docs/api/API_spec.md 즉시 업데이트
- 새 Claude 프롬프트 추가/변경    → docs/architecture/AI_API_Architecture.md + instruction.md 즉시 업데이트
- 핵심 로직 변경 (채점·기억률·진급) → docs/architecture/main_logic.md 즉시 업데이트
- DB 스키마 변경                  → docs/architecture/DB_Schema.md + docs/api/db_schema.sql 즉시 업데이트
- 공유 문서 수정 후               → 프론트엔드 레포로 반드시 동기화 (위 rsync 명령 사용)

문서 업데이트를 기능 구현 이후로 미루는 것은 허용하지 않는다.
기능 구현 커밋과 문서 업데이트 커밋은 같은 세션에 진행한다.
```

---

### 0-2. 중복 문서 관리 규칙 (Single Source of Truth)

```
공유 문서의 원본은 백엔드 레포에만 있다.

[백엔드 docs/ 구조 — SSoT]
docs/
├── instruction.md          ← 이 파일 (SSoT 루트)
├── architecture/
│   ├── main_logic.md
│   ├── AI_API_Architecture.md
│   └── DB_Schema.md
├── api/
│   ├── API_spec.md
│   └── db_schema.sql
├── planning/
│   ├── proposal.md
│   ├── prompt_history.md
│   └── design_UXUI_plan.md
└── ops/
    └── deployment_checklist.md

[프론트엔드 docs/ 구조 — 미러]
docs/
├── instruction.md          ← 백엔드 복사본 (SSoT 안내 포함)
├── main_logic.md           ← 백엔드 복사본
├── AI_API_Architecture.md  ← 백엔드 복사본
├── DB_Schema.md            ← 백엔드 복사본 (선택)
├── API_spec.md             ← 백엔드 복사본
├── prompt_history.md       ← 백엔드 복사본
├── design_UXUI/            ← 프론트 전용
└── design_initial_idea/    ← 프론트 전용

장기 개선 방향: git submodule로 shared-docs 레포를 분리.
```

---

### 0-3. 바이브 코딩 토큰 절감 규칙

```
[파일 접근]
- 파일을 수정하기 전 반드시 해당 파일을 Read로 읽는다.
- 전체 파일이 필요하지 않으면 offset+limit으로 필요한 부분만 읽는다.
- 이미 읽은 파일을 같은 세션에서 다시 읽지 않는다.

[병렬 처리]
- 서로 독립적인 툴 호출은 반드시 병렬로 처리한다.
  예: 백엔드 파일 읽기 + 프론트엔드 파일 읽기 → 동시 호출
  예: 여러 문서 수정 → 각각 Edit 병렬 호출

[편집 전략]
- 기존 파일 수정 → Edit 사용 (Write는 전체 내용을 전송하므로 비효율)
- 신규 파일 생성 또는 전체 재작성만 → Write 사용
- 검색은 Glob/Grep 우선, Bash의 find/grep 사용 금지

[코드 작성 원칙]
- 요청된 범위 밖의 리팩터링, 개선, 주석 추가를 하지 않는다.
- 현재 동작하는 코드를 "개선 목적"으로 건드리지 않는다.
- 에러를 만나면 원인을 파악한 후 최소 범위로 수정한다.
```

---

### 0-4. 커밋 & 푸시 규칙

```
- 기능 구현 완료 후 커밋 시, 관련 문서 업데이트도 같은 커밋 또는 바로 다음 커밋에 포함.
- 백엔드와 프론트엔드 커밋은 같은 세션에서 처리 (문서 불일치 방지).
- 커밋 메시지 형식: "feat/fix/docs/chore: 한국어 설명"
- 공유 문서 동기화 커밋은 별도로: "chore: 백엔드 문서 프론트엔드 동기화"
```

---

## SECTION 1 — 프로젝트 현황 (2026년 4월 기준)

### 1-1. 앱 개요

```
앱 이름: Teach-U (티츄)
핵심 개념: "AI를 가르치면 내가 더 잘 배운다" (프로테제 효과 + 파인만 기법)
차별점: 사용자가 AI 학생 페르소나를 가르치고, 함께 시험을 치르는 역전 구조
과목: 사용자가 직접 정의 (수학 고정 아님 — 어떤 과목이든 가능)
```

### 1-2. 기술 스택

| 레이어 | 기술 |
|--------|------|
| 프론트엔드 | React Native (Expo), TypeScript |
| 백엔드 | FastAPI (Python 3.11), SQLAlchemy async ORM |
| DB | PostgreSQL (Railway 배포) |
| AI | Claude API (claude-sonnet-4-6) |
| 인증 | JWT + Google OAuth |
| 배포 | Railway (백엔드), Expo Go / EAS (프론트엔드) |

### 1-3. 구현 완료 기능

```
[코어 기능 — 완료]
✅ Google 로그인/로그아웃
✅ 과목 생성/수정/삭제
✅ 커리큘럼 항목 관리 (추가/수정/순서변경/삭제)
✅ 단계(Stage) 관리
✅ AI 페르소나 생성 (이름/개성/성별 설정)
✅ 가르치기 세션 (소크라테스 채팅, SSE 스트리밍, 멀티턴)
✅ 세션 종료 후 품질 평가 + 요약 생성 (Claude Haiku)
✅ 단계 시험 (Claude Sonnet 문제 생성, 합산 채점, 진급 판정)
✅ 개념 사물함 (약점 태그 목록)
✅ 약점 복습 (Claude Sonnet 문제 생성 + 퍼지 채점)
✅ 기억률 계산 (에빙하우스 망각 곡선)

[핵심 수치]
- 채팅 max_tokens: 500
- 시험 문제 생성 max_tokens: 1,200
- 시험 통과 기준: combined_score ≥ 70 (user×0.6 + persona×0.4)
- 복습 정답 시: WeakPointTag 삭제 + PersonaMemory.stability += 0.2
- 멀티턴 히스토리: 최근 20개 메시지, 연속 동일 role은 줄바꿈으로 병합
```

### 1-4. 알려진 이슈 / 주의 사항

```
[JSONB 뮤테이션 추적]
SQLAlchemy는 JSONB 컬럼의 인플레이스(in-place) 변경을 자동 감지하지 못한다.
리스트/딕셔너리를 수정한 후 반드시 flag_modified(obj, "field")를 호출한다.

[스트리밍 + DB 세션 수명]
FastAPI의 get_db 의존성은 StreamingResponse 반환 시 라우트 함수가 끝나면 세션을 닫는다.
event_gen() 내부에서 DB 쓰기가 필요하면 async with AsyncSessionLocal() as db: 로 별도 세션을 연다.

[Claude API 멀티턴 제약]
messages 배열의 첫 항목은 반드시 role="user"여야 하고, role이 교대로 나타나야 한다.
연속된 같은 role은 content를 줄바꿈으로 병합한다.

[answer_key 처리]
Claude가 반환하는 answer_key는 "1"~"5" 인덱스 문자열이다.
객관식의 경우 저장 시 실제 보기 텍스트로 변환한다. (프론트는 텍스트를 제출하므로)
```

---

## SECTION 2 — 문서 목록 & 역할

| 경로 | 역할 | SSoT |
|------|------|------|
| `instruction.md` | AI 협업 규칙, 프로젝트 현황, 운영 지침 | 백엔드 루트 |
| `architecture/main_logic.md` | 핵심 구현 로직 (기억률, 시험, 복습 흐름) | 백엔드 |
| `architecture/AI_API_Architecture.md` | Claude API 호출 설계, 프롬프트 7종 명세 | 백엔드 |
| `architecture/DB_Schema.md` | 데이터베이스 스키마 설계 | 백엔드 |
| `api/API_spec.md` | 전체 REST API 명세 | 백엔드 |
| `api/db_schema.sql` | DDL 전체 (PostgreSQL) | 백엔드 |
| `planning/proposal.md` | 공모전 기획 제안서 | 백엔드 |
| `planning/prompt_history.md` | 기획 단계 LLM 대화 기록 | 백엔드 |
| `planning/design_UXUI_plan.md` | UI/UX 화면 설계 | 백엔드 |
| `ops/deployment_checklist.md` | Railway 배포 체크리스트 | 백엔드 |
| `(frontend) design_UXUI/` | 화면별 상세 UX 설계 | 프론트 전용 |
| `(frontend) design_initial_idea/` | 초기 아이디어 기록 | 프론트 전용 |

---

## SECTION 3 — 솔루션 내부 AI 프롬프트 설계 지침

앱 내 Claude API 호출 7종의 설계 원칙과 현행 프롬프트 명세.
상세 템플릿은 `architecture/AI_API_Architecture.md` Section 4를 참조.

---

### Prompt 1: 소크라테스 채팅 (Claude Sonnet / 스트리밍)

**목적**: 사용자가 개념을 설명하면 AI 페르소나가 질문으로만 응답 — 소크라테스 문답법 구현

**설계 원칙**:
1. AI는 절대 답을 먼저 말하지 않는다
2. 개성(Personality) 5종 파라미터에 따라 질문 스타일이 달라진다
3. 페르소나의 현재 기억 상태(memory_context)만 알고 있다고 가정
4. 세션 중 1회 의도적 오류를 삽입하여 사용자의 교정 능력을 테스트
5. **멀티턴**: 단일 메시지가 아닌 messages 배열로 전달 (최근 20개, 연속 동일 role 병합)

**고도화 이력**:

| 버전 | 변경 내용 | 이유 |
|------|---------|------|
| v1 | 단순 "모르는 학생" 페르소나 | 초기 설계 |
| v2 | 개성 4종 파라미터 추가 | 획일적 반응 → 감정 투자 강화 |
| v3 | memory_context 주입 | 페르소나가 배운 것 이상을 알면 비현실적 |
| v4 | 오류 삽입 기능 추가 | 교정 능력 테스트로 이해도 측정 강화 |
| v5 | 멀티턴 messages 배열 방식 전환 | 4번 이후 응답 중단 버그 수정 |

---

### Prompt 2: 시험 문제 생성 (Claude Sonnet)

**목적**: 사용자가 실제로 가르친 내용 + 약점 태그 기반 5문항 자동 생성

**설계 원칙**:
1. 사용자 정의 커리큘럼 기반 — 학년 스펙이 아닌 실제 teaching_sessions 내용에서만 출제
2. weak_point_tags에서 최소 2문항 출제
3. 객관식 answer_key는 인덱스(1~5)가 아닌 실제 보기 텍스트로 변환하여 저장
4. max_tokens=1,200

**고도화 이력**:

| 버전 | 변경 내용 | 이유 |
|------|---------|------|
| v1 | 학년별 교과서 스펙 테이블 기반 출제 | 초기 설계 (수학 고정) |
| v2 | 사용자 수업 내용 기반으로 전환 | 과목 자유화 + "배운 것만 출제" 원칙 |
| v3 | answer_key 인덱스 → 보기 텍스트 변환 추가 | 채점 불일치 버그 수정 |

---

### Prompt 3: AI 학생 시험 응시 (Claude Haiku)

**목적**: 페르소나가 망각 곡선 기반 오답 확률로 시험을 치르는 시뮬레이션

**현행 구현**: 서버에서 홀/짝 번호로 정오답을 결정하는 단순화 로직. Post-MVP에서 Claude 연동 예정.

**망각-오답 확률 매핑**:
```
기억률 ≥ 70%  → 오답 확률 10%
기억률 30~69% → 오답 확률 45%
기억률 < 30%  → 오답 확률 80%
```

---

### Prompt 4: 수업 품질 평가 (Claude Haiku)

**목적**: 세션 종료 시 대화를 4기준(정확성/깊이/예시/완결성)으로 채점

| 버전 | 변경 내용 |
|------|---------|
| v1 | 메시지 길이 기반 단순 점수 계산 |
| v2 | Claude Haiku 호출로 전환, 실제 품질 평가 구현 |

---

### Prompt 5: 세션 요약 생성 (Claude Haiku)

**목적**: 토큰 폭발 방지 — 세션 종료 시 대화 내용을 JSON 요약본으로 압축하여 persona_memory에 저장

---

### Prompt 6: 약점 개념 복습 문제 생성 (Claude Sonnet)

**목적**: 약점 태그 기반 복습 문제 1개 + 힌트 3개 + 핵심 개념 설명 생성

**중요**: `subject_name` 파라미터 필수 — 수학으로 고정하지 않음, 사용자 과목명 사용

---

### Prompt 7: 복습 답변 평가 (Claude Sonnet / 퍼지 채점)

**목적**: 표현이 다소 달라도 핵심 이해를 파악했으면 정답으로 인정하는 유연한 채점

**정답 시 서버 처리**:
1. `WeakPointTag` 삭제
2. `PersonaMemory.stability = min(1.0, stability + 0.2)`

---

## SECTION 4 — 프롬프트 설계 공통 원칙

```
1. 역할 명확화 (Role Clarity)
   → SYSTEM에 AI의 역할, 제약, 금지 사항을 명시적으로 정의

2. 출력 형식 고정 (Structured Output)
   → 모든 프롬프트는 JSON만 출력 요구 → 백엔드 파싱 안정성 확보

3. 과목 중립성 (Subject Agnostic)
   → {subject_name} 파라미터로 동적 주입, 특정 과목 하드코딩 금지

4. 컨텍스트 주입 (Context Injection)
   → 페르소나 메모리, 개성 파라미터를 동적 주입
   → 불필요한 정보는 주입하지 않아 토큰 절약

5. 행동 제약 명시 (Behavioral Constraints)
   → "절대 하지 말아야 할 것"을 명시 (예: 답 먼저 말하지 않기, JSON만 출력)

6. 폴백 처리 (Fallback Handling)
   → Claude가 기대한 형식 반환 실패 시 서버 측 처리 로직 필수
   → 시험 문제 5개 미만 시 서버에서 fallback 문항 보충
```

---

## SECTION 5 — 심사 기준별 AI 활용 전략

```
[기술적 완성도]
- Claude API를 7개의 역할 분리된 프롬프트로 활용
- 각 프롬프트는 역할, 제약, 출력 형식이 명확히 정의됨
- 멀티턴 대화, JSONB 상태 관리, SSE 스트리밍 등 구현 복잡도 높음

[AI활용 능력 및 효율성]
- 모델 티어링: 품질 중요 작업 → Sonnet, 구조화 출력 → Haiku (비용 60~70% 절감)
- 프롬프트 히스토리(planning/prompt_history.md)로 기획 전 과정 문서화

[기획력 및 실무 접합성]
- 교육학 이론(파인만 기법, 에빙하우스 망각 곡선, 프로테제 효과) 기반 설계
- 사용자 정의 커리큘럼 → 어떤 과목이든 적용 가능한 범용 구조

[창의성]
- "AI가 가르친다" → "사용자가 AI를 가르친다"는 역전 구조
- 망각 곡선을 가진 AI 학생 페르소나 + 함께 시험 치르기 = 전례 없는 메커니즘
- 복습 퍼지 채점으로 정확한 표현이 아닌 "이해도" 측정
```

---

*작성: 태훈 × Claude Sonnet 4.6 (바이브코딩)*
*최종 업데이트: 2026-04-12*
