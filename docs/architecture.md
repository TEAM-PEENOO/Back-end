# My Jeja MVP Architecture

## 1) Scope Lock

- Subject: math only
- Level system: 1-9 (elementary 1 to middle school 3)
- Chat: real-time LLM streaming (SSE)
- Exam security: generate -> grade immediately -> purge answer keys
- Deployment: public backend URL required

## 2) High-Level System

```text
React-Native (Expo)
  - Onboarding / Persona / Placement / Teaching / Exam / History
        |
        | HTTPS (JWT)
        v
FastAPI Backend
  - Auth
  - Persona
  - Placement
  - Teaching (SSE stream)
  - Exam
  - Dashboard
  - AI Service (Claude)
  - Forgetting Curve Engine
        |
        +--> PostgreSQL
        |
        +--> Claude API
```

## 3) Backend Module Layout

```text
backend/
  app/
    main.py
    config.py
    deps.py
    db/
      session.py
      models.py
    auth/
      router.py
      service.py
      schemas.py
    persona/
      router.py
      service.py
      schemas.py
    placement/
      router.py
      service.py
      schemas.py
    teaching/
      router.py
      service.py
      schemas.py
    exam/
      router.py
      service.py
      schemas.py
    dashboard/
      router.py
      service.py
      schemas.py
    ai/
      client.py
      prompts.py
      parser.py
    engines/
      forgetting_curve.py
      grading.py
```

## 4) Key Runtime Flows

### A. Teaching with Streaming

1. Client calls `POST /teaching/sessions` with concept.
2. Client sends user message to `POST /teaching/sessions/{id}/messages`.
3. Client calls `POST /teaching/sessions/{id}/stream`.
4. Server builds prompt with:
   - persona profile
   - memory context
   - mistake-injection state (once per session)
5. Server streams tokens as SSE:
   - `event: token`
   - `event: done`
6. Server persists final assistant message.
7. Session finish endpoint runs evaluator and updates weak points/memory.

### B. Secure Exam Grading

1. Create exam with generated questions and internal `answer_key`.
2. User submits all answers.
3. Server grades user answers immediately.
4. Server runs persona-answer simulation and grades.
5. Server computes combined score and level-up rule.
6. Server calls `purge_exam_answer_keys(exam_id)` to remove answer keys.
7. Return only result summary, never return correct answers.

## 5) Security Baseline

- JWT auth for all user endpoints.
- Strong password hashing (`bcrypt`/`argon2`).
- CORS allowlist for Expo and production client only.
- No answer key in API responses.
- Purge answer keys after grading.
- Mask secrets in logs.
- Rate limit on auth and AI-heavy endpoints.

## 6) Deployment (URL Required)

- Backend + Postgres on Railway.
- Public API URL:
  - `https://<service>.up.railway.app/api/v1`
- Environment variables:
  - `DATABASE_URL`
  - `JWT_SECRET`
  - `ANTHROPIC_API_KEY`
  - `APP_ENV=prod`
  - `CORS_ALLOW_ORIGINS`
- Health endpoint:
  - `GET /api/v1/health`

## 7) Non-Goals for MVP

- Offline sync
- Multi-subject support
- Multi-persona per user
- Parent dashboard push delivery
