# Backend Deployment Checklist (Railway)

## 1) Environment Variables

- `DATABASE_URL` (PostgreSQL connection string)
- `REDIS_URL` (rate limit backend)
- `JWT_SECRET` (strong random secret)
- `JWT_ISSUER`
- `JWT_AUDIENCE`
- `ANTHROPIC_API_KEY`
- `ANTHROPIC_MODEL` (default: `claude-3-5-sonnet-latest`)
- `APP_ENV=prod`
- `CORS_ALLOW_ORIGINS` (comma-separated)
- `ALLOWED_HOSTS` (comma-separated)
- `RATE_LIMIT_FAIL_CLOSED` (`true` for strict production)
- `SENTRY_DSN` (recommended)

## 2) Database

- Run migrations in order:
  - `alembic upgrade head`
- Confirm tables exist:
  - `users`, `personas`, `teaching_sessions`, `teaching_messages`
  - `persona_concepts`, `session_weak_points`, `weak_point_tags`
  - `exams`, `exam_questions`, `exam_answers`

## 3) API Health / Security

- `GET /api/v1/health` returns `{ "status": "ok" }`
- Auth endpoints return JWT
- Validate JWT issuer/audience (`iss`, `aud`) on protected routes
- Rate limit works:
  - auth endpoints throttled
  - AI-heavy endpoints throttled
- Multi-instance mode uses Redis-backed counters (not in-memory only)
- Host header validation is active (`ALLOWED_HOSTS`)
- Exam submit purges `exam_questions.answer_key`
- Response security headers present:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Referrer-Policy: no-referrer`
  - `Permissions-Policy`
  - `Cache-Control: no-store`
- `X-Request-ID` response header is present

## 4) Functional Smoke Test

- Register -> login -> create persona
- Start placement -> answer until completed
- Create teaching session -> send message -> stream -> finish
- Create exam -> submit -> receive user/persona/combined score
- Dashboard endpoints return expected data

## 5) Operations Baseline

- Enable Railway logs and error alerts
- Add Sentry (or equivalent) for runtime exception monitoring
- Decide Redis outage policy:
  - strict mode: `RATE_LIMIT_FAIL_CLOSED=true`
  - availability mode: `RATE_LIMIT_FAIL_CLOSED=false` (in-memory fallback)
- Keep API keys out of logs
- Do not expose internal stack traces in API responses
- Audit log events appear for:
  - `auth.register`, `auth.login`
  - `placement.start`, `placement.finish`
  - `exam.submit`
