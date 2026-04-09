import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    CurriculumItem,
    Exam,
    Persona,
    PersonaConcept,
    Stage,
    StageCurriculumItem,
    Subject,
    TeachingSession,
    WeakPointTag,
)
from app.db.session import get_db
from app.deps import get_current_user_id
from app.exam.router import (
    _assert_exam_unlocked_by_stage,
    _create_regular_exam,
    _get_persona,
    grade_exam_submission,
    save_user_answers_only,
)
from app.exam.schemas import CreateExamResponse, SubmitExamRequest, SubmitExamResponse
from app.persona.schemas import CreatePersonaRequest, PersonaResponse, UpdatePersonaRequest
from app.subjects.schemas import (
    CurriculumCreateRequest,
    CurriculumOut,
    StageCreateRequest,
    StageOut,
    SubjectCreateRequest,
    SubjectUpdateRequest,
    SubjectOut,
)
from app.teaching.schemas import CreateTeachingSessionRequest, CreateTeachingSessionResponse, MessageRequest, TeachingResultResponse
from app.teaching.router import add_message as teaching_add_message
from app.teaching.router import create_session as teaching_create_session
from app.teaching.router import finish_session as teaching_finish_session
from app.teaching.router import stream_ai_turn as teaching_stream_ai_turn

router = APIRouter(prefix="/subjects", tags=["Subjects"])


async def _get_subject(db: AsyncSession, *, subject_id: uuid.UUID, user_id: str) -> Subject:
    subject = await db.scalar(select(Subject).where(Subject.id == subject_id, Subject.user_id == user_id))
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    return subject


async def _get_subject_persona(db: AsyncSession, *, subject_id: uuid.UUID, user_id: str) -> Persona:
    persona = await db.scalar(
        select(Persona).where(Persona.user_id == user_id, Persona.subject_id == subject_id)
    )
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    return persona


@router.get("", response_model=list[SubjectOut])
async def list_subjects(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[SubjectOut]:
    rows = (await db.scalars(select(Subject).where(Subject.user_id == user_id).order_by(Subject.created_at.asc()))).all()
    personas = (await db.scalars(select(Persona).where(Persona.user_id == user_id))).all()
    persona_by_subject = {str(p.subject_id): p for p in personas if p.subject_id}
    return [
        SubjectOut(
            id=str(r.id),
            name=r.name,
            description=r.description,
            created_at=r.created_at.isoformat(),
            persona=(
                {
                    "id": str(persona_by_subject[str(r.id)].id),
                    "name": persona_by_subject[str(r.id)].name,
                    "personality": persona_by_subject[str(r.id)].personality,
                    "current_stage_id": str(persona_by_subject[str(r.id)].current_stage_id)
                    if persona_by_subject[str(r.id)].current_stage_id
                    else None,
                }
                if str(r.id) in persona_by_subject
                else None
            ),
        )
        for r in rows
    ]


@router.get("/{subject_id}", response_model=SubjectOut)
async def get_subject(
    subject_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> SubjectOut:
    row = await _get_subject(db, subject_id=subject_id, user_id=user_id)
    persona = await db.scalar(select(Persona).where(Persona.subject_id == row.id, Persona.user_id == user_id))
    return SubjectOut(
        id=str(row.id),
        name=row.name,
        description=row.description,
        created_at=row.created_at.isoformat(),
        persona=(
            {
                "id": str(persona.id),
                "name": persona.name,
                "personality": persona.personality,
                "current_stage_id": str(persona.current_stage_id) if persona.current_stage_id else None,
            }
            if persona
            else None
        ),
    )


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
    return SubjectOut(id=str(row.id), name=row.name, description=row.description, created_at=row.created_at.isoformat())


@router.patch("/{subject_id}", response_model=SubjectOut)
async def patch_subject(
    subject_id: uuid.UUID,
    payload: SubjectUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> SubjectOut:
    row = await _get_subject(db, subject_id=subject_id, user_id=user_id)
    if payload.name is not None:
        row.name = payload.name
    if payload.description is not None:
        row.description = payload.description
    await db.commit()
    await db.refresh(row)
    return SubjectOut(id=str(row.id), name=row.name, description=row.description)


@router.delete("/{subject_id}", status_code=204)
async def delete_subject(
    subject_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    row = await _get_subject(db, subject_id=subject_id, user_id=user_id)
    await db.delete(row)
    await db.commit()


@router.post("/{subject_id}/persona")
async def create_subject_persona(
    subject_id: uuid.UUID,
    payload: CreatePersonaRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    subject = await _get_subject(db, subject_id=subject_id, user_id=user_id)
    existing = await db.scalar(select(Persona).where(Persona.user_id == user_id))
    if existing:
        raise HTTPException(status_code=409, detail="Persona already exists for this user")

    # Path param is authoritative for subject binding; reject mismatched body value.
    if payload.subject_id and payload.subject_id != str(subject_id):
        raise HTTPException(status_code=400, detail="subject_id in body must match path subject_id")

    persona = Persona(
        user_id=user_id,
        subject_id=subject.id,
        name=payload.name,
        personality=payload.personality,
        subject="math",
        current_level=1,
        placement_done=False,
    )
    db.add(persona)
    await db.commit()
    await db.refresh(persona)
    return {
        "id": str(persona.id),
        "subject_id": str(persona.subject_id),
        "name": persona.name,
        "personality": persona.personality,
        "current_stage_id": str(persona.current_stage_id) if persona.current_stage_id else None,
        "created_at": persona.created_at.isoformat(),
    }


@router.get("/{subject_id}/persona")
async def get_subject_persona(
    subject_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    persona = await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)
    return {
        "id": str(persona.id),
        "subject_id": str(persona.subject_id),
        "name": persona.name,
        "personality": persona.personality,
        "current_stage_id": str(persona.current_stage_id) if persona.current_stage_id else None,
        "created_at": persona.created_at.isoformat(),
    }


@router.patch("/{subject_id}/persona")
async def patch_subject_persona(
    subject_id: uuid.UUID,
    payload: UpdatePersonaRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    persona = await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)
    if payload.name is not None:
        persona.name = payload.name
    if payload.personality is not None:
        persona.personality = payload.personality
    await db.commit()
    await db.refresh(persona)
    return {
        "id": str(persona.id),
        "subject_id": str(persona.subject_id),
        "name": persona.name,
        "personality": persona.personality,
        "current_stage_id": str(persona.current_stage_id) if persona.current_stage_id else None,
        "created_at": persona.created_at.isoformat(),
    }


@router.delete("/{subject_id}/persona", status_code=204)
async def delete_subject_persona(
    subject_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    persona = await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)
    await db.delete(persona)
    await db.commit()


@router.post("/{subject_id}/persona/sessions", response_model=CreateTeachingSessionResponse)
async def create_subject_session(
    subject_id: uuid.UUID,
    payload: CreateTeachingSessionRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> CreateTeachingSessionResponse:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)
    class _Req:
        state = type("obj", (), {"request_id": None})()
        headers = {}
        url = None
        method = "POST"
        client = None
    return await teaching_create_session(_Req(), payload, user_id, db)


@router.post("/{subject_id}/persona/sessions/{session_id}/chat")
async def subject_session_chat(
    subject_id: uuid.UUID,
    session_id: uuid.UUID,
    payload: MessageRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)
    await teaching_add_message(session_id, payload, user_id, db)
    return await teaching_stream_ai_turn(session_id, user_id, None, db)


@router.post("/{subject_id}/persona/sessions/{session_id}/end", response_model=TeachingResultResponse)
async def subject_session_end(
    subject_id: uuid.UUID,
    session_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> TeachingResultResponse:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)
    class _Req:
        state = type("obj", (), {"request_id": None})()
        headers = {}
        url = None
        method = "POST"
        client = None
    return await teaching_finish_session(_Req(), session_id, user_id, None, db)


@router.get("/{subject_id}/persona/weak-points")
async def list_subject_weak_points(
    subject_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    persona = await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)
    rows = (
        await db.scalars(
            select(WeakPointTag)
            .where(WeakPointTag.persona_id == persona.id)
            .order_by(desc(WeakPointTag.fail_count), desc(WeakPointTag.last_failed_at))
        )
    ).all()
    return [
        {
            "id": str(r.id),
            "concept": r.concept,
            "fail_count": r.fail_count,
            "last_failed_at": r.last_failed_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/{subject_id}/persona/weak-points/{tag_id}")
async def get_subject_weak_point(
    subject_id: uuid.UUID,
    tag_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    persona = await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)
    row = await db.scalar(select(WeakPointTag).where(WeakPointTag.id == tag_id, WeakPointTag.persona_id == persona.id))
    if not row:
        raise HTTPException(status_code=404, detail="Weak point tag not found")
    return {
        "id": str(row.id),
        "concept": row.concept,
        "fail_count": row.fail_count,
        "last_failed_at": row.last_failed_at.isoformat(),
    }


@router.delete("/{subject_id}/persona/weak-points/{tag_id}", status_code=204)
async def delete_subject_weak_point(
    subject_id: uuid.UUID,
    tag_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    persona = await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)
    row = await db.scalar(select(WeakPointTag).where(WeakPointTag.id == tag_id, WeakPointTag.persona_id == persona.id))
    if not row:
        raise HTTPException(status_code=404, detail="Weak point tag not found")
    await db.delete(row)
    await db.commit()


@router.get("/{subject_id}/persona/exams")
async def list_subject_exams(
    subject_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    persona = await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)
    rows = (
        await db.scalars(
            select(Exam)
            .where(Exam.persona_id == persona.id)
            .order_by(desc(Exam.created_at))
        )
    ).all()
    return [
        {
            "id": str(r.id),
            "stage_id": str(r.stage_id) if r.stage_id else None,
            "user_score": r.user_score,
            "persona_score": r.persona_score,
            "combined_score": r.combined_score,
            "passed": r.passed,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.delete("/{subject_id}/persona/exams/{exam_id}", status_code=204)
async def delete_subject_exam(
    subject_id: uuid.UUID,
    exam_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    persona = await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)
    exam = await db.scalar(select(Exam).where(Exam.id == exam_id, Exam.persona_id == persona.id))
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    if exam.passed is not None:
        raise HTTPException(status_code=403, detail="Completed exam cannot be deleted")
    await db.delete(exam)
    await db.commit()


@router.get("/{subject_id}/persona/exams/{exam_id}")
async def get_subject_exam(
    subject_id: uuid.UUID,
    exam_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    persona = await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)
    exam = await db.scalar(select(Exam).where(Exam.id == exam_id, Exam.persona_id == persona.id))
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    return {
        "id": str(exam.id),
        "stage_id": str(exam.stage_id) if exam.stage_id else None,
        "user_score": exam.user_score,
        "persona_score": exam.persona_score,
        "combined_score": exam.combined_score,
        "passed": exam.passed,
        "created_at": exam.created_at.isoformat(),
        "questions": exam.questions or [],
        "user_answers": exam.user_answers or [],
        "persona_answers": exam.persona_answers or [],
    }


@router.put("/{subject_id}/persona/exams/{exam_id}/user-answers")
async def submit_subject_exam_answers(
    subject_id: uuid.UUID,
    exam_id: uuid.UUID,
    payload: SubmitExamRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)
    await save_user_answers_only(exam_id=exam_id, payload=payload, user_id=user_id, db=db)
    return {"exam_id": str(exam_id), "user_answers_saved": True}


@router.post("/{subject_id}/persona/exams/{exam_id}/grade", response_model=SubmitExamResponse)
async def grade_subject_exam(
    subject_id: uuid.UUID,
    exam_id: uuid.UUID,
    payload: SubmitExamRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> SubmitExamResponse:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)
    class _Req:
        state = type("obj", (), {"request_id": None})()
        headers = {}
        url = None
        method = "POST"
        client = None
    return await grade_exam_submission(request=_Req(), exam_id=exam_id, payload=payload, user_id=user_id, db=db)


@router.get("/{subject_id}/persona/memory")
async def list_subject_persona_memory(
    subject_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    persona = await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)
    rows = (
        await db.scalars(
            select(PersonaConcept)
            .where(PersonaConcept.persona_id == persona.id)
            .order_by(desc(PersonaConcept.last_taught_at))
        )
    ).all()
    return [
        {
            "id": str(r.id),
            "concept": r.concept,
            "summary": r.summary,
            "taught_count": r.taught_count,
            "stability": r.stability,
            "last_taught_at": r.last_taught_at.isoformat(),
            "curriculum_item_id": str(r.curriculum_item_id) if r.curriculum_item_id else None,
        }
        for r in rows
    ]


@router.get("/{subject_id}/persona/memory/{memory_id}")
async def get_subject_persona_memory(
    subject_id: uuid.UUID,
    memory_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    persona = await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)
    row = await db.scalar(
        select(PersonaConcept).where(PersonaConcept.id == memory_id, PersonaConcept.persona_id == persona.id)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {
        "id": str(row.id),
        "concept": row.concept,
        "summary": row.summary,
        "taught_count": row.taught_count,
        "stability": row.stability,
        "last_taught_at": row.last_taught_at.isoformat(),
        "curriculum_item_id": str(row.curriculum_item_id) if row.curriculum_item_id else None,
    }


@router.delete("/{subject_id}/persona/memory/{memory_id}", status_code=204)
async def delete_subject_persona_memory(
    subject_id: uuid.UUID,
    memory_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    persona = await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)
    row = await db.scalar(
        select(PersonaConcept).where(PersonaConcept.id == memory_id, PersonaConcept.persona_id == persona.id)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Memory not found")
    await db.delete(row)
    await db.commit()


@router.get("/{subject_id}/persona/sessions")
async def list_subject_sessions(
    subject_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    persona = await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)
    rows = (
        await db.scalars(
            select(TeachingSession)
            .where(TeachingSession.persona_id == persona.id)
            .order_by(desc(TeachingSession.created_at))
        )
    ).all()
    return [
        {
            "id": str(r.id),
            "persona_id": str(r.persona_id),
            "curriculum_item_id": str(r.curriculum_item_id) if r.curriculum_item_id else None,
            "concept": r.concept,
            "quality_score": r.quality_score,
            "weak_points": r.weak_points or [],
            "summary_generated": r.summary_generated,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/{subject_id}/persona/sessions/{session_id}")
async def get_subject_session(
    subject_id: uuid.UUID,
    session_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    persona = await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)
    row = await db.scalar(select(TeachingSession).where(TeachingSession.id == session_id, TeachingSession.persona_id == persona.id))
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "id": str(row.id),
        "persona_id": str(row.persona_id),
        "curriculum_item_id": str(row.curriculum_item_id) if row.curriculum_item_id else None,
        "concept": row.concept,
        "quality_score": row.quality_score,
        "weak_points": row.weak_points or [],
        "messages": row.messages or [],
        "summary_generated": row.summary_generated,
        "created_at": row.created_at.isoformat(),
    }


@router.delete("/{subject_id}/persona/sessions/{session_id}", status_code=204)
async def delete_subject_session(
    subject_id: uuid.UUID,
    session_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    persona = await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)
    row = await db.scalar(select(TeachingSession).where(TeachingSession.id == session_id, TeachingSession.persona_id == persona.id))
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    await db.delete(row)
    await db.commit()


@router.get("/{subject_id}/curriculum", response_model=list[CurriculumOut])
async def list_curriculum(
    subject_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[CurriculumOut]:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    persona = await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)
    rows = (
        await db.scalars(
            select(CurriculumItem).where(CurriculumItem.subject_id == subject_id).order_by(CurriculumItem.order_index.asc())
        )
    ).all()
    taught_set = set(
        (
            await db.scalars(
                select(func.distinct(TeachingSession.curriculum_item_id)).where(
                    TeachingSession.persona_id == persona.id,
                    TeachingSession.curriculum_item_id.isnot(None),
                )
            )
        ).all()
    )
    return [
        CurriculumOut(
            id=str(r.id),
            subject_id=str(r.subject_id),
            title=r.title,
            note=r.note,
            order_index=r.order_index,
            created_at=r.created_at.isoformat(),
            taught=(r.id in taught_set),
        )
        for r in rows
    ]


@router.get("/{subject_id}/curriculum/{item_id}", response_model=CurriculumOut)
async def get_curriculum_item(
    subject_id: uuid.UUID,
    item_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> CurriculumOut:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    row = await db.scalar(select(CurriculumItem).where(CurriculumItem.id == item_id, CurriculumItem.subject_id == subject_id))
    if not row:
        raise HTTPException(status_code=404, detail="Curriculum item not found")
    return CurriculumOut(
        id=str(row.id),
        subject_id=str(row.subject_id),
        title=row.title,
        note=row.note,
        order_index=row.order_index,
        created_at=row.created_at.isoformat(),
        taught=False,
    )


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
        created_at=row.created_at.isoformat(),
        taught=None,
    )


@router.patch("/{subject_id}/curriculum/{item_id}", response_model=CurriculumOut)
async def patch_curriculum_item(
    subject_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: dict,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> CurriculumOut:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    row = await db.scalar(select(CurriculumItem).where(CurriculumItem.id == item_id, CurriculumItem.subject_id == subject_id))
    if not row:
        raise HTTPException(status_code=404, detail="Curriculum item not found")
    if "title" in payload and payload["title"] is not None:
        row.title = str(payload["title"])
    if "note" in payload:
        row.note = payload["note"]
    if "order_index" in payload and payload["order_index"] is not None:
        row.order_index = int(payload["order_index"])
    await db.commit()
    await db.refresh(row)
    return CurriculumOut(
        id=str(row.id),
        subject_id=str(row.subject_id),
        title=row.title,
        note=row.note,
        order_index=row.order_index,
    )


@router.delete("/{subject_id}/curriculum/{item_id}", status_code=204)
async def delete_curriculum_item(
    subject_id: uuid.UUID,
    item_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    row = await db.scalar(select(CurriculumItem).where(CurriculumItem.id == item_id, CurriculumItem.subject_id == subject_id))
    if not row:
        raise HTTPException(status_code=404, detail="Curriculum item not found")
    await db.delete(row)
    await db.commit()


@router.put("/{subject_id}/curriculum/reorder")
async def reorder_curriculum_items(
    subject_id: uuid.UUID,
    payload: dict,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    order = payload.get("order") or []
    out: list[dict] = []
    for idx, raw_id in enumerate(order):
        try:
            item_id = uuid.UUID(str(raw_id))
        except ValueError:
            continue
        row = await db.scalar(select(CurriculumItem).where(CurriculumItem.id == item_id, CurriculumItem.subject_id == subject_id))
        if not row:
            continue
        row.order_index = idx
        out.append({"id": str(row.id), "order_index": row.order_index})
    await db.commit()
    return out


@router.get("/{subject_id}/stages", response_model=list[StageOut])
async def list_stages(
    subject_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[StageOut]:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    persona = await _get_persona(db, user_id)
    taught_item_set = set(
        (
            await db.scalars(
                select(func.distinct(TeachingSession.curriculum_item_id)).where(
                    TeachingSession.persona_id == persona.id,
                    TeachingSession.curriculum_item_id.isnot(None),
                )
            )
        ).all()
    )
    rows = (await db.scalars(select(Stage).where(Stage.subject_id == subject_id).order_by(Stage.order_index.asc()))).all()
    out: list[StageOut] = []
    for stage in rows:
        stage_links = (
            await db.scalars(select(StageCurriculumItem).where(StageCurriculumItem.stage_id == stage.id))
        ).all()
        item_ids = [link.curriculum_item_id for link in stage_links]
        item_rows = (
            await db.scalars(select(CurriculumItem).where(CurriculumItem.id.in_(item_ids)).order_by(CurriculumItem.order_index.asc()))
        ).all() if item_ids else []
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
                passed_at=stage.passed_at.isoformat() if stage.passed_at else None,
                created_at=stage.created_at.isoformat(),
                curriculum_items=[
                    {
                        "id": str(ci.id),
                        "title": ci.title,
                        "order_index": ci.order_index,
                        "taught": ci.id in taught_item_set,
                    }
                    for ci in item_rows
                ],
                exam_unlocked=(untaught == 0 and total_count > 0),
                untaught_count=untaught,
            )
        )
    return out


@router.get("/{subject_id}/stages/{stage_id}", response_model=StageOut)
async def get_stage(
    subject_id: uuid.UUID,
    stage_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> StageOut:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    persona = await _get_persona(db, user_id)
    stage = await db.scalar(select(Stage).where(Stage.id == stage_id, Stage.subject_id == subject_id))
    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found")
    total = await db.scalar(select(func.count(StageCurriculumItem.id)).where(StageCurriculumItem.stage_id == stage.id))
    taught = await db.scalar(
        select(func.count(func.distinct(TeachingSession.curriculum_item_id)))
        .join(StageCurriculumItem, StageCurriculumItem.curriculum_item_id == TeachingSession.curriculum_item_id)
        .where(StageCurriculumItem.stage_id == stage.id, TeachingSession.persona_id == persona.id)
    )
    total_count = int(total or 0)
    taught_count = int(taught or 0)
    untaught = max(0, total_count - taught_count)
    stage_links = (await db.scalars(select(StageCurriculumItem).where(StageCurriculumItem.stage_id == stage.id))).all()
    item_ids = [link.curriculum_item_id for link in stage_links]
    item_rows = (
        await db.scalars(select(CurriculumItem).where(CurriculumItem.id.in_(item_ids)).order_by(CurriculumItem.order_index.asc()))
    ).all() if item_ids else []
    taught_item_set = set(
        (
            await db.scalars(
                select(func.distinct(TeachingSession.curriculum_item_id)).where(
                    TeachingSession.persona_id == persona.id,
                    TeachingSession.curriculum_item_id.isnot(None),
                )
            )
        ).all()
    )
    return StageOut(
        id=str(stage.id),
        subject_id=str(stage.subject_id),
        name=stage.name,
        order_index=stage.order_index,
        passed=stage.passed,
        passed_at=stage.passed_at.isoformat() if stage.passed_at else None,
        created_at=stage.created_at.isoformat(),
        curriculum_items=[
            {
                "id": str(ci.id),
                "title": ci.title,
                "order_index": ci.order_index,
                "taught": ci.id in taught_item_set,
            }
            for ci in item_rows
        ],
        exam_unlocked=(untaught == 0 and total_count > 0),
        untaught_count=untaught,
    )


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
        passed_at=stage.passed_at.isoformat() if stage.passed_at else None,
        created_at=stage.created_at.isoformat(),
        curriculum_items=[],
        exam_unlocked=False,
        untaught_count=len(payload.curriculum_item_ids),
    )


@router.patch("/{subject_id}/stages/{stage_id}", response_model=StageOut)
async def patch_stage(
    subject_id: uuid.UUID,
    stage_id: uuid.UUID,
    payload: dict,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> StageOut:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    stage = await db.scalar(select(Stage).where(Stage.id == stage_id, Stage.subject_id == subject_id))
    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found")
    if stage.passed:
        raise HTTPException(status_code=403, detail="Passed stage cannot be edited")
    if "name" in payload and payload["name"] is not None:
        stage.name = str(payload["name"])
    if "order_index" in payload and payload["order_index"] is not None:
        stage.order_index = int(payload["order_index"])
    if "curriculum_item_ids" in payload and isinstance(payload["curriculum_item_ids"], list):
        old_links = (await db.scalars(select(StageCurriculumItem).where(StageCurriculumItem.stage_id == stage.id))).all()
        for link in old_links:
            await db.delete(link)
        for raw_id in payload["curriculum_item_ids"]:
            try:
                item_id = uuid.UUID(str(raw_id))
            except ValueError:
                continue
            item = await db.scalar(select(CurriculumItem).where(CurriculumItem.id == item_id, CurriculumItem.subject_id == subject_id))
            if item:
                db.add(StageCurriculumItem(stage_id=stage.id, curriculum_item_id=item_id))
    await db.commit()
    await db.refresh(stage)
    return await get_stage(subject_id, stage_id, user_id, db)


@router.delete("/{subject_id}/stages/{stage_id}", status_code=204)
async def delete_stage(
    subject_id: uuid.UUID,
    stage_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    stage = await db.scalar(select(Stage).where(Stage.id == stage_id, Stage.subject_id == subject_id))
    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found")
    if stage.passed:
        raise HTTPException(status_code=403, detail="Passed stage cannot be deleted")
    await db.delete(stage)
    await db.commit()


@router.put("/{subject_id}/stages/reorder")
async def reorder_stages(
    subject_id: uuid.UUID,
    payload: dict,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    order = payload.get("order") or []
    out: list[dict] = []
    for idx, raw_id in enumerate(order):
        try:
            stage_id = uuid.UUID(str(raw_id))
        except ValueError:
            continue
        row = await db.scalar(select(Stage).where(Stage.id == stage_id, Stage.subject_id == subject_id))
        if not row:
            continue
        row.order_index = idx
        out.append({"id": str(row.id), "order_index": row.order_index})
    await db.commit()
    return out


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


@router.get("/{subject_id}/progress")
async def subject_progress(
    subject_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    subject = await _get_subject(db, subject_id=subject_id, user_id=user_id)
    persona = await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)
    stages = (await db.scalars(select(Stage).where(Stage.subject_id == subject_id).order_by(Stage.order_index.asc()))).all()
    current = None
    if persona.current_stage_id:
        current = await db.scalar(select(Stage).where(Stage.id == persona.current_stage_id, Stage.subject_id == subject_id))
    if not current and stages:
        current = stages[0]

    stage_history = []
    for st in stages:
        exams = (
            await db.scalars(
                select(Exam).where(Exam.persona_id == persona.id, Exam.stage_id == st.id).order_by(Exam.created_at.asc())
            )
        ).all()
        stage_history.append(
            {
                "stage_id": str(st.id),
                "stage_name": st.name,
                "passed": st.passed,
                "passed_at": st.passed_at.isoformat() if st.passed_at else None,
                "exam_scores": [
                    {
                        "exam_id": str(e.id),
                        "combined_score": e.combined_score,
                        "passed": e.passed,
                        "created_at": e.created_at.isoformat(),
                    }
                    for e in exams
                ],
            }
        )

    weak_rows = (
        await db.scalars(select(WeakPointTag).where(WeakPointTag.persona_id == persona.id).order_by(desc(WeakPointTag.fail_count)))
    ).all()
    return {
        "subject": {"id": str(subject.id), "name": subject.name},
        "persona": {"id": str(persona.id), "name": persona.name, "personality": persona.personality},
        "current_stage": {
            "id": str(current.id) if current else None,
            "name": current.name if current else None,
            "order_index": current.order_index if current else None,
        },
        "stage_history": stage_history,
        "weak_points": [{"concept": w.concept, "fail_count": w.fail_count} for w in weak_rows],
    }


@router.get("/{subject_id}/stages/{stage_id}/exam-history")
async def stage_exam_history(
    subject_id: uuid.UUID,
    stage_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    stage = await db.scalar(select(Stage).where(Stage.id == stage_id, Stage.subject_id == subject_id))
    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found")
    persona = await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)
    rows = (
        await db.scalars(
            select(Exam)
            .where(Exam.persona_id == persona.id, Exam.stage_id == stage.id)
            .order_by(Exam.created_at.asc())
        )
    ).all()
    return {
        "stage_id": str(stage.id),
        "stage_name": stage.name,
        "exams": [
            {
                "exam_id": str(e.id),
                "attempt": idx + 1,
                "user_score": e.user_score,
                "persona_score": e.persona_score,
                "combined_score": e.combined_score,
                "passed": e.passed,
                "created_at": e.created_at.isoformat(),
            }
            for idx, e in enumerate(rows)
        ],
    }


