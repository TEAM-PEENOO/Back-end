import random
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Exam, ExamAnswer, ExamQuestion, Persona, WeakPointTag
from app.db.session import get_db
from app.deps import get_current_user_id
from app.placement.schemas import (
    PlacementAnswerRequest,
    PlacementCompletedResponse,
    PlacementInProgressResponse,
    PlacementQuestion,
    PlacementResult,
    PlacementStartResponse,
)


router = APIRouter(prefix="/placement", tags=["Placement"])


def _gen_question(level: int, no: int) -> dict:
    # Minimal placeholder generator. Replace with LLM generation later.
    answer = str(random.randint(1, 5))
    return {
        "question_no": no,
        "content": f"[배치고사 L{level}] 샘플 문제 {no}",
        "options": ["1", "2", "3", "4", "5"],
        "answer_key": answer,
        "concept_tag": f"level_{level}_concept_{no}",
    }


async def _get_persona(db: AsyncSession, user_id: str) -> Persona:
    persona = await db.scalar(select(Persona).where(Persona.user_id == user_id))
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    return persona


@router.post("/start", response_model=PlacementStartResponse)
async def placement_start(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> PlacementStartResponse:
    persona = await _get_persona(db, user_id)
    level = 4
    exam = Exam(persona_id=persona.id, exam_type="placement", level=level)
    db.add(exam)
    await db.flush()

    q = _gen_question(level, 1)
    row = ExamQuestion(
        exam_id=exam.id,
        question_no=q["question_no"],
        type="multiple_choice",
        content=q["content"],
        options=q["options"],
        answer_key=q["answer_key"],
        concept_tag=q["concept_tag"],
        difficulty=2,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    return PlacementStartResponse(
        exam_id=str(exam.id),
        current_level=level,
        question=PlacementQuestion(
            question_id=str(row.id),
            question_no=row.question_no,
            content=row.content,
            options=row.options or [],
        ),
    )


@router.post("/answer", response_model=PlacementInProgressResponse | PlacementCompletedResponse)
async def placement_answer(
    payload: PlacementAnswerRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    persona = await _get_persona(db, user_id)
    exam = await db.scalar(select(Exam).where(Exam.id == payload.exam_id, Exam.persona_id == persona.id, Exam.exam_type == "placement"))
    if not exam:
        raise HTTPException(status_code=404, detail="Placement exam not found")

    q = await db.scalar(select(ExamQuestion).where(ExamQuestion.id == payload.question_id, ExamQuestion.exam_id == exam.id))
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    is_correct = payload.answer.strip() == (q.answer_key or "").strip()
    db.add(ExamAnswer(question_id=q.id, actor="user", answer=payload.answer, is_correct=is_correct))

    # Minimal adaptive flow: max 5 questions for skeleton.
    asked_count = len((await db.scalars(select(ExamQuestion).where(ExamQuestion.exam_id == exam.id))).all())
    next_level = max(1, min(9, exam.level + (1 if is_correct else -1)))

    if asked_count >= 5:
        exam.user_score = 70 if is_correct else 55
        exam.persona_score = 0
        exam.combined_score = exam.user_score
        exam.passed = True
        persona.current_level = next_level
        persona.placement_done = True

        if not is_correct:
            existing = await db.scalar(select(WeakPointTag).where(WeakPointTag.persona_id == persona.id, WeakPointTag.concept == q.concept_tag))
            if existing:
                existing.fail_count += 1
            else:
                db.add(WeakPointTag(persona_id=persona.id, concept=q.concept_tag, fail_count=1))

        await db.commit()
        return PlacementCompletedResponse(
            result=PlacementResult(
                start_level=persona.current_level,
                known_concepts=["기본 사칙연산"],
                weak_concepts=[q.concept_tag] if not is_correct else [],
                summary=f"배치고사 완료. 시작 레벨 {persona.current_level}",
            )
        )

    nq = _gen_question(next_level, asked_count + 1)
    next_row = ExamQuestion(
        exam_id=exam.id,
        question_no=nq["question_no"],
        type="multiple_choice",
        content=nq["content"],
        options=nq["options"],
        answer_key=nq["answer_key"],
        concept_tag=nq["concept_tag"],
        difficulty=2,
    )
    exam.level = next_level
    db.add(next_row)
    await db.commit()
    await db.refresh(next_row)

    return PlacementInProgressResponse(
        current_level=next_level,
        next_question=PlacementQuestion(
            question_id=str(next_row.id),
            question_no=next_row.question_no,
            content=next_row.content,
            options=next_row.options or [],
        ),
    )

