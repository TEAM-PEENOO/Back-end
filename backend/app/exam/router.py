import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import ClaudeClient
from app.ai.prompts import build_exam_questions_prompt
from app.ai.schemas import ExamQuestionSetGen
from app.common.audit import audit_event
from app.common.rate_limit import rate_limit
from app.db.models import Exam, ExamAnswer, ExamQuestion, Persona, PersonaConcept, WeakPointTag
from app.db.session import get_db
from app.deps import get_current_user_id
from app.engines.forgetting_curve import retention_probability
from app.exam.schemas import CreateExamResponse, ExamQuestionOut, SubmitExamRequest, SubmitExamResponse
from app.learning.math_specs import concept_for
from app.personality.profiles import profile_for


router = APIRouter(prefix="/exams", tags=["Exam"])
claude_client = ClaudeClient()


async def _get_persona(db: AsyncSession, user_id: str) -> Persona:
    persona = await db.scalar(select(Persona).where(Persona.user_id == user_id))
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    return persona


def _fallback_question(level: int, no: int) -> dict:
    concept = concept_for(level, no - 1)
    answer_key = str(((level + no) % 5) + 1)
    return {
        "question_no": no,
        "type": "multiple_choice" if no <= 3 else "short_answer",
        "content": f"[정규시험 L{level}] '{concept}' 문제 {no}",
        "options": ["1", "2", "3", "4", "5"] if no <= 3 else None,
        "answer_key": answer_key,
        "concept_tag": f"level_{level}_exam_{concept}",
        "difficulty": 1 if no <= 2 else (2 if no <= 4 else 3),
    }


async def _sample_questions(level: int) -> list[dict]:
    concepts = [concept_for(level, i) for i in range(5)]
    prompt = build_exam_questions_prompt(level=level, concepts=concepts)
    try:
        raw = await claude_client.complete_text(system_prompt=prompt, user_content="JSON only")
        start = raw.find("{")
        end = raw.rfind("}")
        payload = raw[start : end + 1] if start != -1 and end != -1 else raw
        parsed = ExamQuestionSetGen.model_validate_json(payload)
        rows: list[dict] = []
        for i, q in enumerate(parsed.questions, start=1):
            if q.type not in {"multiple_choice", "short_answer"}:
                raise ValueError("invalid question type")
            if q.type == "multiple_choice" and (q.options is None or len(q.options) != 5):
                raise ValueError("mcq requires 5 options")
            rows.append(
                {
                    "question_no": i,
                    "type": q.type,
                    "content": q.content,
                    "options": q.options,
                    "answer_key": q.answer_key.strip(),
                    "concept_tag": q.concept_tag or f"level_{level}_exam_{concept_for(level, i - 1)}",
                    "difficulty": q.difficulty,
                }
            )
        return rows
    except (ValidationError, ValueError, TypeError):
        return [_fallback_question(level, i) for i in range(1, 6)]


def _concept_from_tag(concept_tag: str) -> str:
    if "_exam_" in concept_tag:
        return concept_tag.split("_exam_", 1)[1]
    return concept_tag


def _persona_answer_for(*, correct_answer: str, retention: float, question_type: str) -> tuple[str, str, bool]:
    # Deterministic threshold-based simulation for MVP.
    threshold = 0.7 if question_type == "short_answer" else 0.6
    if retention >= threshold:
        return correct_answer, "어제 배운 내용이 기억나서 자신 있게 풀었어.", True
    # intentionally wrong but deterministic
    wrong = "1" if correct_answer != "1" else "2"
    thought = "헷갈렸어... 비슷한 개념이랑 섞여서 틀린 답을 골랐어."
    return wrong, thought, False


@router.post("", response_model=CreateExamResponse)
async def create_exam(
    request: Request,
    user_id: str = Depends(get_current_user_id),
    _: None = Depends(rate_limit(limit=20, window_sec=60)),
    db: AsyncSession = Depends(get_db),
) -> CreateExamResponse:
    persona = await _get_persona(db, user_id)
    exam = Exam(persona_id=persona.id, exam_type="regular", level=persona.current_level)
    db.add(exam)
    await db.flush()

    generated = await _sample_questions(persona.current_level)
    out_questions: list[ExamQuestionOut] = []
    for q in generated:
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
    audit_event(
        request=request,
        event="exam.create",
        outcome="success",
        user_id=user_id,
        detail=f"exam_id={exam.id},level={exam.level}",
    )

    return CreateExamResponse(exam_id=str(exam.id), level=exam.level, questions=out_questions)


@router.post("/{exam_id}/submit", response_model=SubmitExamResponse)
async def submit_exam(
    request: Request,
    exam_id: uuid.UUID,
    payload: SubmitExamRequest,
    user_id: str = Depends(get_current_user_id),
    _: None = Depends(rate_limit(limit=30, window_sec=60)),
    db: AsyncSession = Depends(get_db),
) -> SubmitExamResponse:
    persona = await _get_persona(db, user_id)
    profile = profile_for(persona.personality)
    exam = await db.scalar(select(Exam).where(Exam.id == exam_id, Exam.persona_id == persona.id, Exam.exam_type == "regular"))
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    if exam.combined_score is not None:
        raise HTTPException(status_code=409, detail="Exam already submitted")

    questions = (await db.scalars(select(ExamQuestion).where(ExamQuestion.exam_id == exam.id))).all()
    q_map = {str(q.id): q for q in questions}
    if not questions:
        raise HTTPException(status_code=400, detail="Exam has no questions")

    if len(payload.answers) != len(questions):
        raise HTTPException(status_code=400, detail="All questions must be answered")

    user_points = 0
    total_points = 0
    weak_updated: list[str] = []
    answered_qids: set[str] = set()
    for item in payload.answers:
        if item.question_id in answered_qids:
            raise HTTPException(status_code=400, detail="Duplicate question answers are not allowed")
        answered_qids.add(item.question_id)
        q = q_map.get(item.question_id)
        if not q:
            raise HTTPException(status_code=400, detail=f"Question not in exam: {item.question_id}")
        weight = 1 if q.type == "multiple_choice" else 2
        total_points += weight
        ok = (item.answer.strip() == (q.answer_key or "").strip())
        if ok:
            user_points += weight
        else:
            weak_updated.append(q.concept_tag)
            existing = await db.scalar(select(WeakPointTag).where(WeakPointTag.persona_id == persona.id, WeakPointTag.concept == q.concept_tag))
            if existing:
                existing.fail_count += 1
            else:
                db.add(WeakPointTag(persona_id=persona.id, concept=q.concept_tag, fail_count=1))
        db.add(ExamAnswer(question_id=q.id, actor="user", answer=item.answer, is_correct=ok))

    user_score = int((user_points / max(total_points, 1)) * 100)

    persona_points = 0
    for q in questions:
        concept = _concept_from_tag(q.concept_tag)
        mem = await db.scalar(
            select(PersonaConcept).where(PersonaConcept.persona_id == persona.id, PersonaConcept.concept == concept)
        )
        retention = (
            retention_probability(last_taught_at=mem.last_taught_at, stability=mem.stability)
            if mem
            else 0.25
        )
        retention = max(0.0, min(1.0, retention * profile.retention_multiplier))
        answer, thought, is_correct = _persona_answer_for(
            correct_answer=q.answer_key or "",
            retention=retention,
            question_type=q.type,
        )
        weight = 1 if q.type == "multiple_choice" else 2
        if is_correct:
            persona_points += weight
        db.add(
            ExamAnswer(
                question_id=q.id,
                actor="persona",
                answer=answer,
                thought=thought,
                is_correct=is_correct,
                created_at=datetime.now(timezone.utc),
            )
        )

    persona_score = int((persona_points / max(total_points, 1)) * 100)
    combined = int((user_score * 0.6) + (persona_score * 0.4))
    passed = (
        combined >= profile.pass_combined
        and user_score >= profile.pass_user_min
        and persona_score >= profile.pass_persona_min
    )

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
    audit_event(
        request=request,
        event="exam.submit",
        outcome="success",
        user_id=user_id,
        detail=f"exam_id={exam.id},combined={combined},passed={passed}",
    )

    return SubmitExamResponse(
        user_score=user_score,
        persona_score=persona_score,
        combined_score=combined,
        passed=passed,
        level_before=level_before,
        level_after=persona.current_level,
        weak_points_updated=weak_updated,
    )

