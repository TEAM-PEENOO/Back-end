import asyncio
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Persona, TeachingMessage, TeachingSession
from app.db.session import get_db
from app.deps import get_current_user_id
from app.teaching.schemas import (
    CreateTeachingSessionRequest,
    CreateTeachingSessionResponse,
    MessageRequest,
    OkResponse,
    TeachingResultResponse,
)


router = APIRouter(prefix="/teaching", tags=["Teaching"])


async def _get_user_persona(db: AsyncSession, user_id: str) -> Persona:
    persona = await db.scalar(select(Persona).where(Persona.user_id == user_id))
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    return persona


@router.post("/sessions", response_model=CreateTeachingSessionResponse)
async def create_session(
    payload: CreateTeachingSessionRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> CreateTeachingSessionResponse:
    persona = await _get_user_persona(db, user_id)
    session = TeachingSession(persona_id=persona.id, concept=payload.concept)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return CreateTeachingSessionResponse(session_id=str(session.id))


@router.post("/sessions/{session_id}/messages", response_model=OkResponse)
async def add_message(
    session_id: uuid.UUID,
    payload: MessageRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> OkResponse:
    persona = await _get_user_persona(db, user_id)
    session = await db.scalar(select(TeachingSession).where(TeachingSession.id == session_id))
    if not session or session.persona_id != persona.id:
        raise HTTPException(status_code=404, detail="Session not found")

    msg = TeachingMessage(session_id=session.id, role="user", content=payload.content)
    db.add(msg)
    await db.commit()
    return OkResponse(ok=True)


@router.post("/sessions/{session_id}/stream")
async def stream_ai_turn(
    session_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    MVP placeholder streaming endpoint (SSE).
    Replace the generator body with Claude streaming tokens later.
    """
    persona = await _get_user_persona(db, user_id)
    session = await db.scalar(select(TeachingSession).where(TeachingSession.id == session_id))
    if not session or session.persona_id != persona.id:
        raise HTTPException(status_code=404, detail="Session not found")

    async def event_gen():
        text = "왜 그렇게 생각했나요? 예시를 하나 들어줄 수 있어요?"
        for ch in text:
            yield "event: token\n"
            yield f"data: {json.dumps({'text': ch}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.01)

        # persist assistant message (non-streaming store for now)
        db_msg = TeachingMessage(session_id=session.id, role="assistant", content=text, created_at=datetime.now(timezone.utc))
        db.add(db_msg)
        await db.commit()

        yield "event: done\n"
        yield "data: {}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.post("/sessions/{session_id}/finish", response_model=TeachingResultResponse)
async def finish_session(
    session_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> TeachingResultResponse:
    persona = await _get_user_persona(db, user_id)
    session = await db.scalar(select(TeachingSession).where(TeachingSession.id == session_id))
    if not session or session.persona_id != persona.id:
        raise HTTPException(status_code=404, detail="Session not found")

    # Placeholder evaluation result. Replace with Prompt E evaluator output.
    session.quality_score = 80
    await db.commit()

    return TeachingResultResponse(
        score=80,
        grade_label="A",
        weak_points=["(todo) concept-gap-1"],
        next_focus="(todo) 다음엔 핵심 규칙을 2가지 예시로 다시 설명해보기",
    )

