from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Exam, Persona, PersonaConcept, TeachingSession, WeakPointTag
from app.engines.forgetting_curve import retention_probability
from app.dashboard.schemas import ExamHistoryItem, HomeResponse, TeachingHistoryItem, WeakPointItem
from app.db.session import get_db
from app.deps import get_current_user_id
from app.personality.profiles import profile_for


router = APIRouter(prefix="", tags=["Dashboard"])


async def _get_persona(db: AsyncSession, user_id: str) -> Persona:
    persona = await db.scalar(select(Persona).where(Persona.user_id == user_id))
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    return persona


@router.get("/dashboard/home", response_model=HomeResponse)
async def home(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> HomeResponse:
    persona = await _get_persona(db, user_id)
    recent_cnt = len((await db.scalars(select(TeachingSession).where(TeachingSession.persona_id == persona.id))).all())
    mem_rows = (await db.scalars(select(PersonaConcept).where(PersonaConcept.persona_id == persona.id))).all()
    if mem_rows:
        vals = [retention_probability(last_taught_at=m.last_taught_at, stability=m.stability) for m in mem_rows]
        retention_summary = round(sum(vals) / len(vals), 3)
    else:
        retention_summary = 0.0
    profile = profile_for(persona.personality)
    return HomeResponse(
        level=persona.current_level,
        retention_summary=retention_summary,
        next_goal=f"정규시험 통과 목표: 합산 {profile.pass_combined}+",
        recent_session_count=recent_cnt,
    )


@router.get("/history/teaching", response_model=list[TeachingHistoryItem])
async def teaching_history(
    limit: int = Query(default=20, ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[TeachingHistoryItem]:
    persona = await _get_persona(db, user_id)
    rows = (
        await db.scalars(
            select(TeachingSession)
            .where(TeachingSession.persona_id == persona.id)
            .order_by(desc(TeachingSession.created_at))
            .limit(limit)
        )
    ).all()
    return [
        TeachingHistoryItem(
            session_id=str(r.id),
            concept=r.concept,
            quality_score=r.quality_score,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]


@router.get("/history/exams", response_model=list[ExamHistoryItem])
async def exam_history(
    limit: int = Query(default=20, ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[ExamHistoryItem]:
    persona = await _get_persona(db, user_id)
    rows = (
        await db.scalars(
            select(Exam)
            .where(Exam.persona_id == persona.id)
            .order_by(desc(Exam.created_at))
            .limit(limit)
        )
    ).all()
    return [
        ExamHistoryItem(
            exam_id=str(r.id),
            exam_type=r.exam_type,
            level=r.level,
            combined_score=r.combined_score,
            passed=r.passed,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]


@router.get("/weak-points", response_model=list[WeakPointItem])
async def weak_points(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[WeakPointItem]:
    persona = await _get_persona(db, user_id)
    rows = (
        await db.scalars(
            select(WeakPointTag)
            .where(WeakPointTag.persona_id == persona.id)
            .order_by(desc(WeakPointTag.fail_count))
        )
    ).all()
    return [
        WeakPointItem(
            concept=r.concept,
            fail_count=r.fail_count,
            last_failed_at=r.last_failed_at.isoformat(),
        )
        for r in rows
    ]

