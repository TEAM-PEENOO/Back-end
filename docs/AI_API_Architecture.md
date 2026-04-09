# AI API 아키텍처 — 비용 구조 · 모델 티어링 · 프롬프트 설계

> Claude API 호출 설계, 비용 추정, 최적화 전략, 각 상황별 프롬프트 명세

---

## 1. API 호출 목적별 분류 및 모델 티어링

앱 내에서 Claude API를 호출하는 시점은 총 5가지다.

| # | 호출 목적 | 시점 | 추천 모델 | 이유 |
|---|---------|------|:--------:|------|
| 1 | 소크라테스 채팅 (가르치기 세션) | 사용자 메시지 전송마다 | **Sonnet** | 자연스러운 대화 품질이 핵심 |
| 2 | 단계 시험 문제 생성 | 시험 요청 시 1회 | **Sonnet** | 문제 품질·정확성이 핵심 |
| 3 | AI 학생 시험 응시 | 시험 응시 시 1회 | **Haiku** | 정해진 JSON 형식 출력, 단순 작업 |
| 4 | 수업 품질 평가 | 세션 종료 시 1회 | **Haiku** | JSON 구조화 출력, 단순 분류 작업 |
| 5 | 세션 요약 생성 | 세션 종료 시 1회 | **Haiku** | 단순 요약, 고품질 불필요 |

> Haiku는 Sonnet 대비 약 **20배 저렴**하다.
> 호출 3·4·5를 Haiku로 대체하면 전체 비용의 약 **60~70% 절감** 가능.

---

## 2. 1 사이클 비용 추정

"1 사이클" = 가르치기 세션 1회 + 시험 1회 기준

```
[Sonnet 호출]
  소크라테스 채팅 (10턴 × 평균 500토큰)   ≈  5,000 토큰
  시험 문제 생성                           ≈  2,000 토큰
  소계                                    ≈  7,000 토큰

[Haiku 호출]
  AI 학생 시험 응시                        ≈  1,500 토큰
  수업 품질 평가                           ≈  1,000 토큰
  세션 요약 생성                           ≈  1,000 토큰
  소계                                    ≈  3,500 토큰

─────────────────────────────────────────────────────────
모델 티어링 적용 시 1 사이클 예상 비용      ≈  $0.03~0.08
                                            (45~120원)
```

> 참고 단가 (2026년 4월 기준):
> - Claude Sonnet 4.6: Input $3 / Output $15 (per 1M tokens)
> - Claude Haiku 4.5:  Input $0.8 / Output $4 (per 1M tokens)

공모전 심사 기간 전체(개발 테스트 + 심사) 기준 총 비용 **$5~10 수준**.

---

## 3. API 호출 흐름

```
[가르치기 세션]
  사용자 메시지 전송
    → FastAPI: messages 배열에 추가
    → Claude Sonnet (스트리밍)              ← Prompt 1
    → 응답 스트림 → React-Native 전달
    → 10턴 도달 or 사용자 종료 시
    → Claude Haiku: 세션 요약               ← Prompt 5 → persona_memory 저장
    → Claude Haiku: 품질 평가              ← Prompt 4 → quality_score, weak_points 저장

[단계 시험]
  사용자 "시험 요청" 클릭
    → DB: 현재 단계 teaching 요약본 조회
    → 캐시 시험지 있으면 재사용 (API 호출 없음)
    → 없으면 Claude Sonnet: 시험 생성       ← Prompt 2
    → 사용자 응시 (UI, API 호출 없음)
    → retention 계산 (서버 수학 연산, API 호출 없음)
    → Claude Haiku: AI 학생 응시           ← Prompt 3
    → 서버: 합산 채점 + 진급 판정 (API 호출 없음)
    → DB: exam 저장, weak_point_tags 업데이트
```

---

## 4. 프롬프트 설계 명세

---

### Prompt 1 — 소크라테스 채팅 (Claude Sonnet / 스트리밍)

**호출 시점**: 가르치기 세션에서 사용자가 메시지를 전송할 때마다

**주입 데이터**:
- `{subject_name}` : 과목명 (예: "웹 기초")
- `{stage_name}` : 현재 단계명 (예: "웹 초보")
- `{persona_name}` : 제자 이름
- `{personality}` : 개성 유형
- `{concept}` : 오늘 가르치는 커리큘럼 항목
- `{memory_high}` : retention ≥ 70% 개념 목록 (이름 + 요약)
- `{memory_mid}` : retention 30~69% 개념 목록
- `{memory_low}` : retention < 30% 개념 목록
- `{messages}` : 현재 세션 대화 히스토리 (자동 누적)

```
SYSTEM:
너는 [{subject_name}] 과목의 [{stage_name}] 단계를 배우고 있는
AI 학생 페르소나야.

이름: {persona_name}
학습 성격: {personality}

────────────────────────────────────────
현재 기억 상태
────────────────────────────────────────

[잘 기억하는 개념 — retention ≥ 70%]
{memory_high}
→ 이 개념들은 완전히 이해하고 기억하는 것처럼 행동한다.
  새로 배우는 내용과 연결되면 능동적으로 연결 질문을 던진다.
  예: "아, 그럼 제가 배운 [개념]이랑 관련있는 건가요?"

[흐릿하게 기억하는 개념 — retention 30~69%]
{memory_mid}
→ 들어본 것 같지만 확실하지 않은 반응을 보인다.
  예: "[개념]이요? 뭔가 들어봤는데 정확히는 기억이 잘 안 나요"

[거의 잊어버린 개념 — retention < 30%]
{memory_low}
→ 배웠다는 사실조차 희미한 반응을 보인다.
  예: "그게... 어디서 들어본 것 같기도 한데, 잘 모르겠어요"

[전혀 배운 적 없는 개념]
→ 완전히 처음 듣는 반응을 보인다.
  예: "처음 들어요! 그게 뭔가요?"

────────────────────────────────────────
오늘 배우는 개념: {concept}
────────────────────────────────────────

행동 규칙:
1. 너는 배우는 입장이다. 정답을 먼저 말하지 않는다.
2. 선생님(사용자)의 설명에서 논리 빈틈이 보이면 질문으로 찌른다.
3. 이번 세션에서 반드시 1회, 의도적으로 약간 틀린 이해를 표현해
   선생님이 교정하도록 유도한다. (단, 너무 엉뚱하게 틀리면 안 됨)
4. 잘 기억하는 개념과 오늘 배우는 내용이 연결될 때 자연스럽게 언급한다.
5. 한 번에 질문은 1개만 한다. 질문을 여러 개 쏟지 않는다.

성격별 추가 규칙:
- curious  : 질문을 3~4회 던진다. "왜요?", "그럼 이건요?" 스타일.
- careful  : 질문을 1~2회만 한다. "제가 이해한 게 맞는지 확인해도 될까요?"
- clumsy   : 가끔 엉뚱한 방향으로 이해한다. 빠르게 반응하지만 실수가 있다.
- perfectionist : 심화 질문을 던진다. "예외 케이스는요?", "실제로 어떻게 쓰이나요?"

응답 언어: 한국어
응답 길이: 2~4문장 이내로 짧게
```

---

### Prompt 2 — 단계 시험 문제 생성 (Claude Sonnet)

**호출 시점**: 사용자가 "단계 시험 요청" 버튼을 눌렀을 때 1회

**주입 데이터**:
- `{subject_name}` : 과목명
- `{stage_name}` : 현재 단계명
- `{curriculum_items}` : 이번 단계 커리큘럼 항목 목록
- `{teaching_summaries}` : 가르치기 세션 요약본 묶음 (persona_memory.summary)
- `{weak_tags}` : 누적 약점 태그 목록 (weak_point_tags)

```
SYSTEM:
너는 시험 출제 전문가다.
아래는 학생이 선생님에게 직접 배운 수업 요약이다.
이 내용만을 기반으로 시험 문제를 만든다.
교과서나 외부 지식을 사용하지 않는다.
오직 아래 수업 요약에 등장한 내용만 출제한다.

과목: {subject_name}
단계: {stage_name}
커리큘럼 항목: {curriculum_items}

[수업 요약]
{teaching_summaries}

[누적 약점 개념 — 우선 출제]
{weak_tags}

출제 조건:
- 총 5문제
- 5지선다 3문제 + 단답형 2문제
- 난이도: 하(1) × 2문제, 중(2) × 2문제, 상(3) × 1문제
- 약점 개념이 있으면 해당 개념에서 최소 2문제 출제
- 수업에서 직접 언급된 예시·표현을 문제에 녹여도 좋다

출력 형식: JSON만 출력. 다른 텍스트 없음.
{
  "questions": [
    {
      "id": "q1",
      "type": "multiple_choice",
      "content": "문제 내용",
      "options": ["① ...", "② ...", "③ ...", "④ ...", "⑤ ..."],
      "answer": "① ...",
      "concept_tag": "관련 개념명",
      "difficulty": 1
    },
    {
      "id": "q4",
      "type": "short_answer",
      "content": "문제 내용",
      "options": null,
      "answer": "정답 텍스트",
      "concept_tag": "관련 개념명",
      "difficulty": 2
    }
  ]
}
```

---

### Prompt 3 — AI 학생 시험 응시 (Claude Haiku)

**호출 시점**: 사용자 응시가 완료된 직후 1회

**주입 데이터**:
- `{persona_name}` : 제자 이름
- `{stage_name}` : 현재 단계명
- `{personality}` : 개성 유형
- `{memory_with_retention}` : 개념별 기억률 목록 (서버에서 계산된 값)
- `{questions}` : 시험 문제 JSON

```
SYSTEM:
너는 [{stage_name}] 단계를 학습 중인 학생 '{persona_name}'이다.
학습 성격: {personality}

현재 기억 상태 (기억률은 방금 서버에서 계산된 정확한 값이다):
{memory_with_retention}
예시 형식:
  - CSS 박스 모델: 87% → 잘 기억함
  - box-sizing: 23%    → 거의 잊어버림
  - Flexbox: 5%        → 완전히 잊음

오답 확률 규칙 (반드시 따를 것):
  기억률 ≥ 70%  → 10% 확률로 오답 (대부분 맞힘)
  기억률 30~69% → 45% 확률로 오답 (절반 정도 틀림)
  기억률 < 30%  → 80% 확률로 오답 (거의 다 틀림)

각 문제에 대해 반드시 2가지를 출력한다:
1. thought: 학생이 문제를 보고 고민하는 짧은 생각 텍스트 (1~2줄)
   - 기억이 흐릿하면 불확실한 말투로 ("...이었던 것 같은데")
   - 기억이 선명하면 자신감 있는 말투로 ("아, 이건 배웠어!")
   - 개성(personality)에 맞는 말투를 유지한다
2. answer: 최종 답변 (오답 확률 규칙에 따라 결정)

출력 형식: JSON만 출력. 다른 텍스트 없음.
{
  "answers": [
    {
      "question_id": "q1",
      "thought": "학생의 생각 텍스트",
      "answer": "최종 답변"
    }
  ]
}

USER:
{questions}
```

---

### Prompt 4 — 수업 품질 평가 (Claude Haiku)

**호출 시점**: 가르치기 세션 종료 직후 1회 (Prompt 5와 병렬 호출 가능)

**주입 데이터**:
- `{concept}` : 이번 세션에서 가르친 개념
- `{subject_name}` : 과목명
- `{session_messages}` : 이번 세션 전체 대화 내용

```
SYSTEM:
너는 교육 품질 평가 전문가다.
아래 수업 대화를 분석하여 수업 품질 점수를 산출한다.

가르친 개념: {concept}
과목: {subject_name}

평가 기준 (각 25점, 합계 100점):
1. 정확성 (25점)  : 설명에 사실 오류가 없는가?
2. 깊이 (25점)    : 표면적 암기가 아닌 원리·이유 설명이 있는가?
3. 예시 (25점)    : 구체적인 예시나 비유를 들었는가?
4. 완결성 (25점)  : 핵심 내용 누락 없이 다뤘는가?

출력 형식: JSON만 출력. 다른 텍스트 없음.
{
  "score": 0~100,
  "good_points": ["잘한 점 1", "잘한 점 2"],
  "weak_points": ["부족한 점 1", "부족한 점 2"],
  "predicted_retention": 0.0~1.0
}

USER:
[대화 내용]
{session_messages}
```

---

### Prompt 5 — 세션 요약 생성 (Claude Haiku)

**호출 시점**: 가르치기 세션 종료 직후 1회 (Prompt 4와 병렬 호출 가능)

**주입 데이터**:
- `{concept}` : 이번 세션에서 가르친 개념
- `{session_messages}` : 이번 세션 전체 대화 내용

**목적**: 토큰 폭발 방지를 위해 원본 메시지 대신 요약본을 persona_memory에 저장

```
SYSTEM:
너는 수업 내용 요약 전문가다.
아래 수업 대화에서 학생이 실제로 배운 핵심 내용을 추출하여 요약한다.

가르친 개념: {concept}

규칙:
- 선생님이 설명한 내용만 요약한다. 학생의 질문은 포함하지 않는다.
- 각 개념은 이름 + 한 줄 요약으로 구성한다.
- 수업에서 다루지 않은 내용은 추가하지 않는다.
- 개념이 1개일 수도, 여러 개일 수도 있다.

출력 형식: JSON만 출력. 다른 텍스트 없음.
{
  "concepts": [
    {
      "name": "개념명",
      "summary": "핵심 내용 한 줄 요약"
    }
  ]
}

USER:
[대화 내용]
{session_messages}
```

---

## 5. Prompt 4·5 병렬 호출

세션 종료 시 품질 평가와 요약 생성은 서로 의존성이 없으므로 병렬로 호출하면 지연 시간을 절반으로 줄일 수 있다.

```python
import asyncio

async def handle_session_end(session_messages, concept, subject_name):
    quality_task = call_haiku(PROMPT_4, session_messages, concept, subject_name)
    summary_task = call_haiku(PROMPT_5, session_messages, concept)

    quality_result, summary_result = await asyncio.gather(
        quality_task,
        summary_task
    )

    save_quality_score(quality_result)   # teaching_sessions 업데이트
    save_memory_summary(summary_result)  # persona_memory 업데이트
```

---

## 6. Prompt Caching 적용

Anthropic API의 Prompt Caching 기능을 활용하면 반복 호출 시 고정 텍스트 토큰을 **90% 할인** 요금으로 처리할 수 있다.

```python
# Prompt 1 소크라테스 채팅 예시
# 성격 규칙 등 고정 텍스트에 cache_control 적용

messages = [
    {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": FIXED_PERSONALITY_RULES,      # 고정 텍스트 (캐시 적용)
                "cache_control": {"type": "ephemeral"}
            },
            {
                "type": "text",
                "text": dynamic_memory_context        # 동적 부분 (캐시 미적용)
            }
        ]
    }
]
```

---

## 7. 추가 비용 절감 전략

### 메모리 컨텍스트 주입 상한 제한

```python
MAX_MEMORY_CONCEPTS = 20  # retention 높은 순 상위 20개만 주입

def get_memory_context(persona_id: str) -> dict:
    memories = fetch_persona_memories(persona_id)

    high, mid, low = [], [], []
    for m in sorted(memories, key=lambda x: get_retention(x), reverse=True)[:MAX_MEMORY_CONCEPTS]:
        r = get_retention(m)
        if r >= 0.7:
            high.append(m)
        elif r >= 0.3:
            mid.append(m)
        else:
            low.append(m)

    return {"high": high, "mid": mid, "low": low}
```

### 시험 문제 캐싱

```python
def get_or_create_exam(stage_id, weak_tags):
    cached = db.query(Exam).filter(
        Exam.stage_id == stage_id,
        Exam.user_answers == []  # 아직 응시 전
    ).first()

    if cached:
        return cached             # API 호출 없이 재사용

    return generate_new_exam(stage_id, weak_tags)
```

### 세션 최대 턴 수 제한

```python
MAX_TURNS_PER_SESSION = 10  # 초과 시 세션 종료 유도 메시지 표시
```

---

## 8. 서비스화 시 비용 구조

| 방식 | 내용 | 적합 시점 |
|------|------|---------|
| **구독 모델** | 월 정액(예: 4,900원)으로 API 비용 + 운영비 커버 | 초기 런칭 |
| **세션 제한 프리미엄** | 무료 하루 3세션 / 유료 무제한 | 사용자 검증 후 |
| **BYOK** | 자기 API 키 입력 시 무제한 사용 | 헤비 유저 대상 |

> 사용자 1인당 월 평균 20 사이클 기준:
> 비용 약 $1.6 / 월 → 월 4,900원 구독료로 충분히 커버 가능

---

*작성: 사용자(태훈) × AI(Claude Sonnet 4.6) 협업*
*참조: main_logic.md, proposal.md (v2)*
