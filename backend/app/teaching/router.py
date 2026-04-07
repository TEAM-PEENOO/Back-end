import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import ClaudeClient
from app.ai.prompts import build_socratic_system_prompt, build_teaching_evaluator_prompt
from app.common.audit import audit_event
from app.common.rate_limit import rate_limit
from app.db.models import Persona, PersonaConcept, SessionWeakPoint, TeachingMessage, TeachingSession, WeakPointTag
from app.db.session import get_db
from app.deps import get_current_user_id
from app.personality.profiles import profile_for
from app.teaching.schemas import (
    CreateTeachingSessionRequest,
    CreateTeachingSessionResponse,
    MessageRequest,
    OkResponse,
    TeachingResultResponse,
)


router = APIRouter(prefix="/teaching", tags=["Teaching"])
claude_client = ClaudeClient()


class EvaluationResult(BaseModel):
    score: int = Field(ge=0, le=100)
    grade_label: str
    weak_points: list[str] = Field(default_factory=list)
    next_focus: str
    predicted_retention: float = Field(ge=0.0, le=1.0)


async def _get_user_persona(db: AsyncSession, user_id: str) -> Persona:
    persona = await db.scalar(select(Persona).where(Persona.user_id == user_id))
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    return persona


@router.post("/sessions", response_model=CreateTeachingSessionResponse)
async def create_session(
    request: Request,
    payload: CreateTeachingSessionRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> CreateTeachingSessionResponse:
    persona = await _get_user_persona(db, user_id)
    session = TeachingSession(persona_id=persona.id, concept=payload.concept)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    audit_event(
        request=request,
        event="teaching.session.start",
        outcome="success",
        user_id=user_id,
        detail=f"session_id={session.id},concept={payload.concept}",
    )
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
    _: None = Depends(rate_limit(limit=30, window_sec=60)),
    db: AsyncSession = Depends(get_db),
):
    persona = await _get_user_persona(db, user_id)
    session = await db.scalar(select(TeachingSession).where(TeachingSession.id == session_id))
    if not session or session.persona_id != persona.id:
        raise HTTPException(status_code=404, detail="Session not found")

    async def event_gen():
        latest_user = await db.scalar(
            select(TeachingMessage)
            .where(TeachingMessage.session_id == session.id, TeachingMessage.role == "user")
            .order_by(TeachingMessage.created_at.desc())
        )
        user_text = latest_user.content if latest_user else session.concept
        system_prompt = build_socratic_system_prompt(
            persona_name=persona.name,
            personality=persona.personality,
            concept=session.concept,
        )

        chunks: list[str] = []
        try:
            async for token in claude_client.stream_text(system_prompt=system_prompt, user_content=user_text):
                chunks.append(token)
                yield "event: token\n"
                yield f"data: {json.dumps({'text': token}, ensure_ascii=False)}\n\n"
        except Exception:
            fallback = "좋아. 방금 설명을 한 문장으로 다시 요약해줄래?"
            chunks = [fallback]
            yield "event: token\n"
            yield f"data: {json.dumps({'text': fallback}, ensure_ascii=False)}\n\n"

        text = "".join(chunks).strip() or "좋아, 계속 설명해줘."
        db_msg = TeachingMessage(session_id=session.id, role="assistant", content=text, created_at=datetime.now(timezone.utc))
        db.add(db_msg)
        await db.commit()

        yield "event: done\n"
        yield "data: {}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.post("/sessions/{session_id}/finish", response_model=TeachingResultResponse)
async def finish_session(
    request: Request,
    session_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    _: None = Depends(rate_limit(limit=30, window_sec=60)),
    db: AsyncSession = Depends(get_db),
) -> TeachingResultResponse:
    persona = await _get_user_persona(db, user_id)
    session = await db.scalar(select(TeachingSession).where(TeachingSession.id == session_id))
    if not session or session.persona_id != persona.id:
        raise HTTPException(status_code=404, detail="Session not found")

    rows = (
        await db.scalars(
            select(TeachingMessage)
            .where(TeachingMessage.session_id == session.id)
            .order_by(TeachingMessage.created_at.asc())
        )
    ).all()
    transcript = "\n".join(f"{m.role}: {m.content}" for m in rows)

    eval_prompt = build_teaching_evaluator_prompt(concept=session.concept, transcript=transcript)
    raw = await claude_client.complete_text(system_prompt=eval_prompt, user_content="JSON only")
    try:
        start = raw.find("{")
        end = raw.rfind("}")
        parsed = json.loads(raw[start : end + 1] if start != -1 and end != -1 else raw)
        eval_result = EvaluationResult.model_validate(parsed)
    except (json.JSONDecodeError, ValidationError, ValueError, TypeError):
        eval_result = EvaluationResult.model_validate({
            "score": 80,
            "grade_label": "A",
            "weak_points": ["핵심 예시 부족"],
            "next_focus": "핵심 규칙과 반례를 1개씩 설명해보기",
            "predicted_retention": 0.75,
        })

    score = eval_result.score
    grade_label = eval_result.grade_label
    weak_points = eval_result.weak_points[:5]
    next_focus = eval_result.next_focus
    predicted_retention = eval_result.predicted_retention

    session.quality_score = score
    session.predicted_retention = predicted_retention

    # Persist session weak points + cumulative weak tags
    for wp in weak_points:
        db.add(SessionWeakPoint(session_id=session.id, concept=wp))
        existing = await db.scalar(
            select(WeakPointTag).where(WeakPointTag.persona_id == persona.id, WeakPointTag.concept == wp)
        )
        if existing:
            existing.fail_count += 1
            existing.last_failed_at = datetime.now(timezone.utc)
        else:
            db.add(WeakPointTag(persona_id=persona.id, concept=wp, fail_count=1, last_failed_at=datetime.now(timezone.utc)))

    # Update persona concept memory
    profile = profile_for(persona.personality)
    mem = await db.scalar(
        select(PersonaConcept).where(PersonaConcept.persona_id == persona.id, PersonaConcept.concept == session.concept)
    )
    if mem:
        mem.taught_count += 1
        gain = predicted_retention * 0.3 * profile.learning_gain
        mem.stability = max(1.0, mem.stability * (1.0 + gain) * profile.memory_bonus)
        mem.last_taught_at = datetime.now(timezone.utc)
    else:
        db.add(
            PersonaConcept(
                persona_id=persona.id,
                concept=session.concept,
                taught_count=1,
                stability=max(1.0, (1.0 + predicted_retention * profile.learning_gain) * profile.memory_bonus),
                last_taught_at=datetime.now(timezone.utc),
            )
        )

    await db.commit()
    audit_event(
        request=request,
        event="teaching.session.finish",
        outcome="success",
        user_id=user_id,
        detail=f"session_id={session.id},score={score},retention={predicted_retention}",
    )

    return TeachingResultResponse(
        score=score,
        grade_label=grade_label,
        weak_points=weak_points,
        next_focus=next_focus,
    )

