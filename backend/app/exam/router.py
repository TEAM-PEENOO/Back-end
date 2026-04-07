import random
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Exam, ExamAnswer, ExamQuestion, Persona, WeakPointTag
from app.db.session import get_db
from app.deps import get_current_user_id
from app.exam.schemas import CreateExamResponse, ExamQuestionOut, SubmitExamRequest, SubmitExamResponse


router = APIRouter(prefix="/exams", tags=["Exam"])


async def _get_persona(db: AsyncSession, user_id: str) -> Persona:
    persona = await db.scalar(select(Persona).where(Persona.user_id == user_id))
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    return persona


def _sample_question(level: int, no: int) -> dict:
    answer_key = str(random.randint(1, 5))
    return {
        "question_no": no,
        "type": "multiple_choice" if no <= 3 else "short_answer",
        "content": f"[정규시험 L{level}] 샘플 문제 {no}",
        "options": ["1", "2", "3", "4", "5"] if no <= 3 else None,
        "answer_key": answer_key if no <= 3 else "sample",
        "concept_tag": f"level_{level}_exam_{no}",
        "difficulty": 1 if no <= 2 else (2 if no <= 4 else 3),
    }


@router.post("", response_model=CreateExamResponse)
async def create_exam(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> CreateExamResponse:
    persona = await _get_persona(db, user_id)
    exam = Exam(persona_id=persona.id, exam_type="regular", level=persona.current_level)
    db.add(exam)
    await db.flush()

    out_questions: list[ExamQuestionOut] = []
    for i in range(1, 6):
        q = _sample_question(persona.current_level, i)
        row = ExamQuestion(
            exam_id=exam.id,
            question_no=q["question_no"],
            type=q["type"],
            content=q["content"],
            options=q["options"],
            answer_key=q["answer_key"],
            concept_tag=q["concept_tag"],
            difficulty=q["difficulty"],
        )
        db.add(row)
        await db.flush()
        out_questions.append(
            ExamQuestionOut(
                question_id=str(row.id),
                question_no=row.question_no,
                type=row.type,
                content=row.content,
                options=row.options,
            )
        )
    await db.commit()

    return CreateExamResponse(exam_id=str(exam.id), level=exam.level, questions=out_questions)


@router.post("/{exam_id}/submit", response_model=SubmitExamResponse)
async def submit_exam(
    exam_id: uuid.UUID,
    payload: SubmitExamRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> SubmitExamResponse:
    persona = await _get_persona(db, user_id)
    exam = await db.scalar(select(Exam).where(Exam.id == exam_id, Exam.persona_id == persona.id, Exam.exam_type == "regular"))
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    questions = (await db.scalars(select(ExamQuestion).where(ExamQuestion.exam_id == exam.id))).all()
    q_map = {str(q.id): q for q in questions}
    if not questions:
        raise HTTPException(status_code=400, detail="Exam has no questions")

    user_correct = 0
    weak_updated: list[str] = []
    for item in payload.answers:
        q = q_map.get(item.question_id)
        if not q:
            continue
        ok = (item.answer.strip() == (q.answer_key or "").strip())
        if ok:
            user_correct += 1
        else:
            weak_updated.append(q.concept_tag)
            existing = await db.scalar(select(WeakPointTag).where(WeakPointTag.persona_id == persona.id, WeakPointTag.concept == q.concept_tag))
            if existing:
                existing.fail_count += 1
            else:
                db.add(WeakPointTag(persona_id=persona.id, concept=q.concept_tag, fail_count=1))
        db.add(ExamAnswer(question_id=q.id, actor="user", answer=item.answer, is_correct=ok))

    user_score = int((user_correct / max(len(questions), 1)) * 100)

    # Persona score placeholder: random around retention assumptions.
    persona_score = max(20, min(95, user_score - random.randint(5, 30)))
    combined = int((user_score * 0.6) + (persona_score * 0.4))
    passed = combined >= 75 and user_score >= 50 and persona_score >= 30

    level_before = persona.current_level
    if passed and persona.current_level < 9:
        persona.current_level += 1

    exam.user_score = user_score
    exam.persona_score = persona_score
    exam.combined_score = combined
    exam.passed = passed

    # Security policy: drop answer keys right after grading.
    for q in questions:
        q.answer_key = None

    await db.commit()

    return SubmitExamResponse(
        user_score=user_score,
        persona_score=persona_score,
        combined_score=combined,
        passed=passed,
        level_before=level_before,
        level_after=persona.current_level,
        weak_points_updated=weak_updated,
    )

