# My Jeja Backend (Skeleton)

This folder is a runnable FastAPI skeleton based on:
- `docs/db_schema.sql`
- `docs/api_spec.yaml`
- `docs/architecture.md`

## Run locally

Create venv and install:

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Set env:

```bash
copy .env.example .env
```

Start server:

```bash
uvicorn app.main:app --reload --port 8000
```

Open:
- Health: `http://localhost:8000/api/v1/health`
- Docs: `http://localhost:8000/docs`

## DB migration (Alembic)

Run initial migration:

```bash
alembic upgrade head
```

Create new migration after model changes:

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

## Notes

- Teaching stream endpoint uses Claude streaming tokens with fallback behavior.
- Placement/Exam question generation uses Claude JSON output with deterministic fallback.
- Security baseline includes Redis rate limiting, JWT issuer/audience validation, security headers, trusted hosts, and structured audit logs.
- Before deploy, configure `REDIS_URL` and `SENTRY_DSN` in `.env`.
- Google OAuth login endpoints:
  - `GET /api/v1/auth/google?redirect_uri=...` (backend-managed redirect flow)
  - `GET /api/v1/auth/google/callback` (Google callback)
  - `POST /api/v1/auth/google` (id_token login for mobile/web)
  - `GET /api/v1/auth/google/url` + `POST /api/v1/auth/google/code` (web redirect flow)
- For Google-only auth mode set:
  - `AUTH_GOOGLE_ONLY=true`
  - `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_OAUTH_REDIRECT_URI`, `GOOGLE_APP_REDIRECT_DEFAULT`
- `DATABASE_URL` can be either `postgresql://...` or `postgresql+asyncpg://...` (backend normalizes automatically).
