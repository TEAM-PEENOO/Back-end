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
