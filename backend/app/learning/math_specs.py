LEVEL_CONCEPTS: dict[int, list[str]] = {
    1: ["한 자리 수 덧셈", "한 자리 수 뺄셈", "기본 도형"],
    2: ["두 자리 수 덧셈", "두 자리 수 뺄셈", "구구단 기초"],
    3: ["세 자리 수 사칙연산", "분수 기초", "소수 기초"],
    4: ["큰 수", "각도", "소수 덧셈/뺄셈"],
    5: ["약수와 배수", "분수 사칙연산", "합동/대칭"],
    6: ["분수 나눗셈", "소수 나눗셈", "비와 비율"],
    7: ["소인수분해", "정수와 유리수", "일차방정식"],
    8: ["연립방정식", "부등식", "일차함수"],
    9: ["제곱근", "이차방정식", "이차함수"],
}


def concept_for(level: int, idx: int) -> str:
    concepts = LEVEL_CONCEPTS.get(level, LEVEL_CONCEPTS[4])
    return concepts[idx % len(concepts)]

