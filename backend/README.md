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

## Notes

- The teaching stream endpoint is a placeholder SSE generator. Replace with Claude streaming tokens.
- DB models are a minimal subset; expand as you implement placement/exam features.
