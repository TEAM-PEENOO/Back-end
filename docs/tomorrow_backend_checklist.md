# Tomorrow Backend Checklist (2026-04-08 Wrap-up)

## What is already strong

- FastAPI skeleton with auth/persona/teaching/placement/exam/dashboard routes is runnable.
- Adaptive placement and regular exam scoring logic are implemented with deterministic fallback.
- LLM integration supports streaming (teaching) and JSON validation (question/evaluation generation).
- Security baseline exists: JWT issuer/audience checks, security headers, trusted host, Redis rate limit, answer-key purge.
- Core docs are aligned: `db_schema.sql`, `api_spec.yaml`, `architecture.md`.

## Remaining gaps to prioritize next

1. Sentry operation policy finalization
- Define sampling (`traces_sample_rate`) and ignore/filter list for expected 4xx noise.
- Add environment-specific policy (local/staging/prod) and confirm DSN wiring in deployment.

2. Audit log destination hardening
- Current audit is structured but stdout-based.
- Forward logs to a centralized sink (e.g., CloudWatch, ELK, Datadog) and set retention/search policy.

3. Question quality guardrails
- Add stricter coverage checks for generated questions (concept diversity/difficulty spread).
- Reject and regenerate when quality thresholds are not met.

4. Test coverage for risk paths
- Add integration tests for: duplicate submit (409), rate-limit 429, answer-key purge after grading.
- Add contract tests for key response schemas in `api_spec.yaml`.

5. Deployment verification runbook
- Smoke test checklist after deploy: auth, placement, teaching stream, exam submit, dashboard.
- Add rollback and incident response notes.

## Today improvements added in this wrap-up

- Added missing audit events:
  - `teaching.session.start`
  - `teaching.session.finish`
  - `exam.create`
- Added rate limiting to exam creation endpoint.
- Updated backend README notes to reflect current implementation status.
