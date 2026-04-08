import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CurriculumItem, Stage, StageCurriculumItem, Subject, TeachingSession
from app.db.session import get_db
from app.deps import get_current_user_id
from app.exam.router import _assert_exam_unlocked_by_stage, _create_regular_exam, _get_persona
from app.exam.schemas import CreateExamResponse
from app.subjects.schemas import (
    CurriculumCreateRequest,
    CurriculumOut,
    StageCreateRequest,
    StageOut,
    SubjectCreateRequest,
    SubjectOut,
)

router = APIRouter(prefix="/subjects", tags=["Subjects"])


async def _get_subject(db: AsyncSession, *, subject_id: uuid.UUID, user_id: str) -> Subject:
    subject = await db.scalar(select(Subject).where(Subject.id == subject_id, Subject.user_id == user_id))
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    return subject


@router.get("", response_model=list[SubjectOut])
async def list_subjects(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[SubjectOut]:
    rows = (await db.scalars(select(Subject).where(Subject.user_id == user_id).order_by(Subject.created_at.asc()))).all()
    return [SubjectOut(id=str(r.id), name=r.name, description=r.description) for r in rows]


@router.post("", response_model=SubjectOut)
async def create_subject(
    payload: SubjectCreateRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> SubjectOut:
    row = Subject(user_id=user_id, name=payload.name, description=payload.description)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return SubjectOut(id=str(row.id), name=row.name, description=row.description)


@router.get("/{subject_id}/curriculum", response_model=list[CurriculumOut])
async def list_curriculum(
    subject_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[CurriculumOut]:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    rows = (
        await db.scalars(
            select(CurriculumItem).where(CurriculumItem.subject_id == subject_id).order_by(CurriculumItem.order_index.asc())
        )
    ).all()
    return [
        CurriculumOut(
            id=str(r.id),
            subject_id=str(r.subject_id),
            title=r.title,
            note=r.note,
            order_index=r.order_index,
        )
        for r in rows
    ]


@router.post("/{subject_id}/curriculum", response_model=CurriculumOut)
async def add_curriculum_item(
    subject_id: uuid.UUID,
    payload: CurriculumCreateRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> CurriculumOut:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    order_idx = payload.order_index
    if order_idx is None:
        max_idx = await db.scalar(select(func.max(CurriculumItem.order_index)).where(CurriculumItem.subject_id == subject_id))
        order_idx = int(max_idx or 0) + 1
    row = CurriculumItem(
        subject_id=subject_id,
        title=payload.title,
        note=payload.note,
        order_index=order_idx,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return CurriculumOut(
        id=str(row.id),
        subject_id=str(row.subject_id),
        title=row.title,
        note=row.note,
        order_index=row.order_index,
    )


@router.get("/{subject_id}/stages", response_model=list[StageOut])
async def list_stages(
    subject_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[StageOut]:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    persona = await _get_persona(db, user_id)
    rows = (await db.scalars(select(Stage).where(Stage.subject_id == subject_id).order_by(Stage.order_index.asc()))).all()
    out: list[StageOut] = []
    for stage in rows:
        total = await db.scalar(
            select(func.count(StageCurriculumItem.id)).where(StageCurriculumItem.stage_id == stage.id)
        )
        taught = await db.scalar(
            select(func.count(func.distinct(TeachingSession.curriculum_item_id)))
            .join(StageCurriculumItem, StageCurriculumItem.curriculum_item_id == TeachingSession.curriculum_item_id)
            .where(StageCurriculumItem.stage_id == stage.id, TeachingSession.persona_id == persona.id)
        )
        total_count = int(total or 0)
        taught_count = int(taught or 0)
        untaught = max(0, total_count - taught_count)
        out.append(
            StageOut(
                id=str(stage.id),
                subject_id=str(stage.subject_id),
                name=stage.name,
                order_index=stage.order_index,
                passed=stage.passed,
                exam_unlocked=(untaught == 0 and total_count > 0),
                untaught_count=untaught,
            )
        )
    return out


@router.post("/{subject_id}/stages", response_model=StageOut)
async def create_stage(
    subject_id: uuid.UUID,
    payload: StageCreateRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> StageOut:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    order_idx = payload.order_index
    if order_idx is None:
        max_idx = await db.scalar(select(func.max(Stage.order_index)).where(Stage.subject_id == subject_id))
        order_idx = int(max_idx or 0) + 1
    stage = Stage(subject_id=subject_id, name=payload.name, order_index=order_idx)
    db.add(stage)
    await db.flush()

    for raw_id in payload.curriculum_item_ids:
        try:
            item_id = uuid.UUID(raw_id)
        except ValueError:
            continue
        item = await db.scalar(select(CurriculumItem).where(CurriculumItem.id == item_id, CurriculumItem.subject_id == subject_id))
        if item:
            db.add(StageCurriculumItem(stage_id=stage.id, curriculum_item_id=item_id))

    await db.commit()
    await db.refresh(stage)
    return StageOut(
        id=str(stage.id),
        subject_id=str(stage.subject_id),
        name=stage.name,
        order_index=stage.order_index,
        passed=stage.passed,
        exam_unlocked=False,
        untaught_count=len(payload.curriculum_item_ids),
    )


@router.post("/{subject_id}/stages/{stage_id}/exams", response_model=CreateExamResponse)
async def create_stage_exam(
    subject_id: uuid.UUID,
    stage_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> CreateExamResponse:
    subject = await _get_subject(db, subject_id=subject_id, user_id=user_id)
    stage = await db.scalar(select(Stage).where(Stage.id == stage_id, Stage.subject_id == subject.id))
    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found")

    persona = await _get_persona(db, user_id)
    if persona.subject_id and persona.subject_id != subject.id:
        raise HTTPException(status_code=403, detail="Persona is bound to another subject")
    await _assert_exam_unlocked_by_stage(db, persona_id=persona.id, stage_id=stage.id)

    stage_item_ids = (
        await db.scalars(select(StageCurriculumItem.curriculum_item_id).where(StageCurriculumItem.stage_id == stage.id))
    ).all()
    stage_items = (
        await db.scalars(select(CurriculumItem.title).where(CurriculumItem.id.in_(stage_item_ids)))
    ).all() if stage_item_ids else []
    level_hint = max(1, min(9, len(stage_items) or persona.current_level))

    class _Req:
        state = type("obj", (), {"request_id": None})()
        headers = {}
        url = None
        method = "POST"
        client = None

    return await _create_regular_exam(
        request=_Req(),
        db=db,
        persona=persona,
        user_id=user_id,
        level=level_hint,
        stage_id=stage.id,
    )
