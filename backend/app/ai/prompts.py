def build_socratic_system_prompt(*, persona_name: str, personality: str, concept: str) -> str:
    return (
        "너는 학습자 페르소나다. 답을 직접 말하지 말고 질문으로만 반응해라.\n"
        f"- 이름: {persona_name}\n"
        f"- 개성: {personality}\n"
        f"- 주제: {concept}\n"
        "규칙:\n"
        "1) 왜/어떻게/예시를 묻는 질문 위주\n"
        "2) 정답을 단정하지 말 것\n"
        "3) 1~2문장으로 간결하게 답할 것\n"
        "개성별 말투:\n"
        "- curious: 질문이 많고 활발함\n"
        "- careful: 꼼꼼하고 확인 질문 위주\n"
        "- clumsy: 가끔 급하게 잘못 이해함\n"
        "- perfectionist: 예외/심화 질문을 자주 함\n"
        "- steady: 반응은 느리지만 복습하면 오래 기억하는 타입"
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


def build_placement_question_prompt(*, level: int, concept: str) -> str:
    return (
        "한국 교육과정 수학 배치고사 문제 1개를 JSON으로만 생성해라.\n"
        f"레벨: {level} (1=초1 ... 9=중3)\n"
        f"개념: {concept}\n"
        "스키마:\n"
        '{"content":"","options":["","","","",""],"answer_key":"1","concept_tag":""}\n'
        "조건: options는 5개, answer_key는 1~5 문자열."
    )


def build_exam_questions_prompt(
    *,
    level: int,
    taught_concepts: list[str],
    weak_tags: list[str],
) -> str:
    taught_text = ", ".join(taught_concepts) if taught_concepts else "없음"
    weak_text = ", ".join(weak_tags) if weak_tags else "없음"
    return (
        "학생이 실제로 가르친 내용 기반의 수학 정규시험 5문항을 JSON으로만 생성해라.\n"
        f"레벨: {level} (1=초1 ... 9=중3)\n"
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
        "- 오직 '학생이 학습한 개념' 범위 안에서만 출제"
    )

