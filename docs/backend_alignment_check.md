# Backend Alignment Check (2026-04-08)

## 기준 문서
- `docs/proposal.md`
- `docs/instruction.md`
- `docs/db_schema.sql`
- `docs/api_spec.yaml`
- `docs/architecture.md`

## 현재 일치 상태

- [x] 수학 단일 과목, 레벨 1~9 범위 고정
- [x] JWT 인증 + 기본 라우터 구성
- [x] 배치고사 CAT 종료 규칙(최대 12문항 + 레벨 수렴)
- [x] 가르치기 채팅 SSE 스트리밍
- [x] 시험 제출 시 정답키 폐기
- [x] Alembic 초기/추가 마이그레이션 구성
- [x] 약점 태그 누적
- [x] 세션 종료 평가값을 메모리(stability) 업데이트에 반영
- [x] 개성 시스템 5종(steady 포함) 파라미터를 학습/기억/시험 통과조건에 반영

## 남은 핵심 TODO

- [x] Prompt E 평가 출력을 더 엄격히 검증(Pydantic JSON schema)
- [x] persona 응시(생각 텍스트 + 기억률 기반 오답 확률) 정식 구현
- [x] 망각 곡선 `retention = exp(-t / stability)` 계산 엔진 추가
- [x] 문제 생성을 LLM JSON 출력으로 전환(실패 시 규칙 기반 fallback)
- [~] Redis 기반 rate limit + 핵심 audit log 적용 완료, Sentry/운영 관측 보강 진행 중

## 기획 대비 확장/차이

- 기존 기획 문서의 개성 4종을 실사용 파라미터 기준으로 5종으로 확장
  - 추가 타입: `steady` (느리게 학습, 오래 기억)
  - 앱 운영 관점에서 학습 지속성 개선을 위한 확장
