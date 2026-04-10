import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import build_socratic_system_prompt
from app.common.audit import audit_event
from app.common.rate_limit import rate_limit
from app.common.weak_points import upsert_weak_point_tag
from app.db.models import Persona, PersonaConcept, TeachingSession
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


class EvaluationResult(BaseModel):
    score: int = Field(ge=0, le=100)
    grade_label: str
    weak_points: list[str] = Field(default_factory=list)
    next_focus: str
    predicted_retention: float = Field(ge=0.0, le=1.0)


def _local_persona_reply(*, personality: str, concept: str, user_text: str) -> str:
    text = user_text.strip()
    if not text:
        return f"{concept}에서 핵심 규칙을 한 문장으로 먼저 알려줄래?"

    prompts = {
        "curious": "좋아! 그러면 왜 그렇게 되는지 예시 한 개로 더 설명해줄래?",
        "careful": "내가 이해한 게 맞는지 확인하고 싶어. 핵심만 다시 정리해줄래?",
        "clumsy": "잠깐 헷갈렸어. 이 부분을 틀리기 쉬운 포인트 기준으로 다시 알려줘!",
        "perfectionist": "좋아. 예외 케이스 하나랑 기본 케이스 하나를 같이 비교해줄래?",
        "steady": "천천히 복습하고 싶어. 방금 설명에서 꼭 기억할 한 줄만 알려줘.",
    }
    suffix = prompts.get(personality, prompts["careful"])
    return f"방금 설명 잘 들었어. {suffix}"


def _evaluate_session_locally(rows: list[dict]) -> EvaluationResult:
    user_lines = [r for r in rows if r.get("role") == "user"]
    total_chars = sum(len(str(r.get("content", ""))) for r in user_lines)
    asks_question = any("?" in str(r.get("content", "")) for r in user_lines)

    if total_chars >= 300:
        score = 90
    elif total_chars >= 180:
        score = 80
    elif total_chars >= 90:
        score = 70
    else:
        score = 60

    weak_points: list[str] = []
    if len(user_lines) < 2:
        weak_points.append("설명 반복 부족")
    if not asks_question:
        weak_points.append("확인 질문 부족")
    if total_chars < 120:
        weak_points.append("예시 밀도 부족")

    grade = "A" if score >= 85 else ("B" if score >= 70 else "C")
    predicted_retention = max(0.45, min(0.95, score / 100))
    next_focus = "핵심 규칙 1개와 반례 1개를 함께 설명해보기"

    return EvaluationResult(
        score=score,
        grade_label=grade,
        weak_points=weak_points[:5],
        next_focus=next_focus,
        predicted_retention=predicted_retention,
    )


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
    curriculum_item_id = None
    if payload.curriculum_item_id:
        try:
            curriculum_item_id = uuid.UUID(payload.curriculum_item_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid curriculum_item_id")
    session = TeachingSession(persona_id=persona.id, curriculum_item_id=curriculum_item_id, concept=payload.concept)
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

    messages = list(session.messages or [])
    messages.append(
        {
            "role": "user",
            "content": payload.message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
    session.messages = messages
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
        latest_user = next((m for m in reversed(list(session.messages or [])) if m.get("role") == "user"), None)
        user_text = str(latest_user.get("content")) if latest_user else session.concept
        _ = build_socratic_system_prompt(
            persona_name=persona.name,
            personality=persona.personality,
            concept=session.concept,
        )
        text = _local_persona_reply(personality=persona.personality, concept=session.concept, user_text=user_text)
        chunks = [text]
        yield "event: token\n"
        yield f"data: {json.dumps({'text': text}, ensure_ascii=False)}\n\n"

        text = "".join(chunks).strip() or "좋아, 계속 설명해줘."
        messages = list(session.messages or [])
        messages.append(
            {
                "role": "assistant",
                "content": text,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        session.messages = messages
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

    rows = list(session.messages or [])
    eval_result = _evaluate_session_locally(rows)

    score = eval_result.score
    grade_label = eval_result.grade_label
    weak_points = eval_result.weak_points[:5]
    next_focus = eval_result.next_focus
    predicted_retention = eval_result.predicted_retention

    session.quality_score = score
    session.weak_points = weak_points
    session.summary_generated = True
    # Prevent token blow-up: keep only short recent context.
    session.messages = (session.messages or [])[-12:]

    # Persist only cumulative weak tags (single source of truth).
    for wp in weak_points:
        await upsert_weak_point_tag(db, persona_id=persona.id, concept=wp)

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

