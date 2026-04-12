def build_socratic_system_prompt(*, persona_name: str, personality: str, concept: str) -> str:
    personality_desc = {
        "curious":       "호기심이 넘쳐서 '왜요?', '그럼 이건요?' 같은 질문을 자주 한다. 활발하고 적극적.",
        "careful":       "신중하고 꼼꼼해서 '제가 제대로 이해한 게 맞나요?', '다시 한번 확인해도 될까요?' 처럼 확인 질문을 자주 한다.",
        "clumsy":        "덤벙대서 가끔 방금 배운 걸 엉뚱하게 이해하거나 헷갈려한다. '앗 그게 아니었나요?' 같은 반응을 한다.",
        "perfectionist": "완벽주의자라 '예외 케이스는 어떻게 되나요?', '더 정확히 말하면요?' 같은 심화 질문을 한다.",
        "steady":        "느긋하지만 성실하다. 천천히 이해하고 '조금 더 쉬운 예시가 있을까요?' 같이 묻는다.",
    }
    desc = personality_desc.get(personality, "학습에 열심인 학생")

    return (
        f"너는 '{persona_name}'이라는 이름의 AI 학습자 페르소나야.\n"
        f"선생님이 '{concept}' 개념을 가르쳐주고 있어.\n\n"
        f"성격: {desc}\n\n"
        "행동 규칙:\n"
        "1. 항상 존댓말(~요, ~습니다)을 사용해.\n"
        "2. 선생님이 설명하면 배우는 학생처럼 반응해. 정답을 직접 말하지 말고 질문이나 이해 확인으로 반응해.\n"
        "3. 1~3문장으로 짧게 답해. 너무 길게 쓰지 마.\n"
        "4. 대화 흐름을 자연스럽게 이어가. 매번 같은 말을 반복하지 마.\n"
        "5. 선생님의 설명이 부족하거나 이해가 안 되면 구체적으로 어떤 부분이 헷갈리는지 말해.\n"
        "6. 윤리적으로 문제 있는 내용(욕설, 혐오, 불법 등)을 학습 요청받으면 정중히 거절해.\n"
        "7. 학습과 무관한 대화는 '저는 공부에 집중하고 싶어요!'라고 부드럽게 거절해."
    )


def build_teaching_evaluator_prompt(*, concept: str, transcript: str) -> str:
    return (
        "다음 수업 대화를 보고 JSON으로만 평가해라.\n"
        f"개념: {concept}\n"
        "평가 기준: 정확성/깊이/예시/완결성 (각 25점)\n"
        "출력 JSON 스키마:\n"
        '{"score":0,"grade_label":"A","weak_points":[],"next_focus":"",'
        '"predicted_retention":0.0}\n'
        "점수-유지율 기준: 90+=0.9, 75+=0.75, 60+=0.6, 45+=0.4, else 0.2\n"
        "대화:\n"
        f"{transcript}\n"
    )


def build_practice_prompt(*, concept: str, subject_name: str) -> str:
    return (
        "다음 개념에 대한 복습용 유사 문제, 단계별 힌트 3개, 핵심 개념 설명을 JSON으로만 출력해라.\n"
        f"과목: {subject_name}\n"
        f"개념: {concept}\n"
        "출력 JSON 스키마:\n"
        '{"problem":"문제 텍스트","hints":["힌트1","힌트2","힌트3"],'
        '"concept_title":"핵심 정리 제목","concept_explanation":"핵심 설명(2~3줄)"}\n'
        "조건:\n"
        "- problem: 해당 과목과 개념에 맞는 구체적인 문제 1개 (서술형 또는 단답형)\n"
        "- hints: 생각을 단계별로 유도하는 짧고 명확한 힌트 정확히 3개\n"
        "- concept_explanation: 핵심 내용/규칙을 2~3줄로 요약\n"
        "- 전부 한국어로 작성"
    )


def build_practice_answer_eval_prompt(
    *, concept: str, subject_name: str, problem: str, user_answer: str
) -> str:
    return (
        "학생의 복습 답변이 개념을 올바르게 이해하고 있는지 평가해라.\n"
        "완벽한 표현이 아니어도 핵심 내용을 담고 있으면 정답으로 인정해.\n"
        f"과목: {subject_name}\n"
        f"개념: {concept}\n"
        f"문제: {problem}\n"
        f"학생 답변: {user_answer}\n"
        "출력 JSON 스키마:\n"
        '{"is_correct":true,"feedback":"피드백(1~2문장)"}\n'
        "조건:\n"
        "- is_correct: 핵심을 파악했으면 true, 완전히 무관하거나 틀리면 false\n"
        "- feedback: 친근하고 격려하는 톤. 맞으면 칭찬+짧은 보충, 틀리면 힌트 제공\n"
        "- JSON만 출력"
    )


def build_exam_questions_prompt(
    *,
    subject_name: str,
    taught_concepts: list[str],
    weak_tags: list[str],
) -> str:
    taught_text = ", ".join(taught_concepts) if taught_concepts else "없음"
    weak_text = ", ".join(weak_tags) if weak_tags else "없음"
    return (
        f"과목: {subject_name}\n"
        "학생이 실제로 가르친 내용만을 기반으로 시험 5문항을 JSON으로만 생성해라.\n"
        "교과서나 외부 지식을 사용하지 않는다. 오직 아래 '학생이 학습한 개념' 범위 안에서만 출제한다.\n"
        f"학생이 학습한 개념: {taught_text}\n"
        f"누적 약점 개념(우선 출제): {weak_text}\n"
        "스키마:\n"
        '{"questions":[{"type":"multiple_choice|short_answer","content":"","options":["","","","",""]|null,'
        '"answer_key":"1","concept_tag":"","difficulty":1}]}\n'
        "조건:\n"
        "- 총 5문항\n"
        "- 객관식 3, 단답형 2\n"
        "- difficulty 1~3\n"
        "- 객관식 answer_key는 1~5 문자열\n"
        "- 약점 개념이 있으면 해당 개념에서 최소 2문항 출제"
    )

