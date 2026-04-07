import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import ClaudeClient
from app.ai.prompts import build_placement_question_prompt
from app.ai.schemas import PlacementQuestionGen
from app.common.audit import audit_event
from app.db.models import Exam, ExamAnswer, ExamQuestion, Persona, WeakPointTag
from app.db.session import get_db
from app.deps import get_current_user_id
from app.learning.math_specs import concept_for
from app.placement.schemas import (
    PlacementAnswerRequest,
    PlacementCompletedResponse,
    PlacementInProgressResponse,
    PlacementQuestion,
    PlacementResult,
    PlacementStartResponse,
)


router = APIRouter(prefix="/placement", tags=["Placement"])
claude_client = ClaudeClient()


def _fallback_question(level: int, no: int) -> dict:
    # Deterministic placeholder generator. Replace with LLM generation later.
    answer = str(((level + no) % 5) + 1)
    concept = concept_for(level, no - 1)
    return {
        "question_no": no,
        "content": f"[배치고사 L{level}] '{concept}' 관련 문제 {no}",
        "options": ["1", "2", "3", "4", "5"],
        "answer_key": answer,
        "concept_tag": f"level_{level}_concept_{concept}",
    }


async def _gen_question(level: int, no: int) -> dict:
    concept = concept_for(level, no - 1)
    prompt = build_placement_question_prompt(level=level, concept=concept)
    try:
        raw = await claude_client.complete_text(system_prompt=prompt, user_content="JSON only")
        start = raw.find("{")
        end = raw.rfind("}")
        payload = raw[start : end + 1] if start != -1 and end != -1 else raw
        parsed = PlacementQuestionGen.model_validate_json(payload)
        answer_key = parsed.answer_key.strip()
        if answer_key not in {"1", "2", "3", "4", "5"}:
            raise ValueError("invalid answer key")
        return {
            "question_no": no,
            "content": parsed.content,
            "options": parsed.options,
            "answer_key": answer_key,
            "concept_tag": parsed.concept_tag or f"level_{level}_concept_{concept}",
        }
    except (ValidationError, ValueError, TypeError):
        return _fallback_question(level, no)


def _extract_level(concept_tag: str) -> int | None:
    if concept_tag.startswith("level_") and "_concept_" in concept_tag:
        raw = concept_tag.split("_concept_", 1)[0].replace("level_", "")
        if raw.isdigit():
            return int(raw)
    return None


def _should_finish(
    *,
    asked_count: int,
    current_level: int,
    answer_history: list[tuple[int, bool]],
) -> bool:
    """
    CAT stopping rules:
    - max 12 questions
    - same level answered correctly twice in a row
    - same level answered incorrectly twice in a row
    """
    if asked_count >= 12:
        return True
    if len(answer_history) < 2:
        return False

    (prev_level, prev_ok), (last_level, last_ok) = answer_history[-2], answer_history[-1]
    same_level = prev_level == current_level and last_level == current_level
    if not same_level:
        return False
    return (prev_ok and last_ok) or ((not prev_ok) and (not last_ok))


async def _get_persona(db: AsyncSession, user_id: str) -> Persona:
    persona = await db.scalar(select(Persona).where(Persona.user_id == user_id))
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    return persona


@router.post("/start", response_model=PlacementStartResponse)
async def placement_start(
    request: Request,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> PlacementStartResponse:
    persona = await _get_persona(db, user_id)
    level = 4
    exam = Exam(persona_id=persona.id, exam_type="placement", level=level)
    db.add(exam)
    await db.flush()

    q = await _gen_question(level, 1)
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
    audit_event(request=request, event="placement.start", outcome="success", user_id=user_id, detail=f"exam_id={exam.id}")

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
    request: Request,
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
    existing_answer = await db.scalar(
        select(ExamAnswer).where(ExamAnswer.question_id == q.id, ExamAnswer.actor == "user")
    )
    if existing_answer:
        raise HTTPException(status_code=409, detail="Answer already submitted for this question")
    db.add(ExamAnswer(question_id=q.id, actor="user", answer=payload.answer, is_correct=is_correct))

    questions = (await db.scalars(select(ExamQuestion).where(ExamQuestion.exam_id == exam.id).order_by(ExamQuestion.question_no))).all()
    answers = (
        await db.scalars(
            select(ExamAnswer)
            .join(ExamQuestion, ExamQuestion.id == ExamAnswer.question_id)
            .where(ExamQuestion.exam_id == exam.id, ExamAnswer.actor == "user")
            .order_by(ExamQuestion.question_no)
        )
    ).all()
    asked_count = len(questions)
    user_correct_count = sum(1 for a in answers if a.is_correct is True)

    # Build (level, is_correct) history by question order
    q_by_id = {str(qq.id): qq for qq in questions}
    answer_history: list[tuple[int, bool]] = []
    for a in answers:
        qq = q_by_id.get(str(a.question_id))
        if not qq:
            continue
        q_level = _extract_level(qq.concept_tag) or exam.level
        answer_history.append((q_level, bool(a.is_correct)))

    current_level = _extract_level(q.concept_tag) or exam.level
    next_level = max(1, min(9, current_level + (1 if is_correct else -1)))

    if _should_finish(asked_count=asked_count, current_level=current_level, answer_history=answer_history):
        exam.user_score = int((user_correct_count / max(asked_count, 1)) * 100)
        exam.persona_score = 0
        exam.combined_score = exam.user_score
        exam.passed = True
        # Placement result uses converged level:
        # - two correct at same level -> keep current
        # - two wrong at same level -> drop one
        if len(answer_history) >= 2:
            (_, prev_ok), (_, last_ok) = answer_history[-2], answer_history[-1]
            if prev_ok and last_ok:
                persona.current_level = current_level
            elif (not prev_ok) and (not last_ok):
                persona.current_level = max(1, current_level - 1)
            else:
                persona.current_level = next_level
        else:
            persona.current_level = next_level
        persona.placement_done = True

        if not is_correct:
            existing = await db.scalar(select(WeakPointTag).where(WeakPointTag.persona_id == persona.id, WeakPointTag.concept == q.concept_tag))
            if existing:
                existing.fail_count += 1
            else:
                db.add(WeakPointTag(persona_id=persona.id, concept=q.concept_tag, fail_count=1))

        await db.commit()
        audit_event(
            request=request,
            event="placement.finish",
            outcome="success",
            user_id=user_id,
            detail=f"exam_id={exam.id},start_level={persona.current_level}",
        )
        return PlacementCompletedResponse(
            result=PlacementResult(
                start_level=persona.current_level,
                known_concepts=[f"level_{max(persona.current_level - 1, 1)}_baseline"],
                weak_concepts=[q.concept_tag] if not is_correct else [],
                summary=f"배치고사 완료 ({asked_count}문항). 시작 레벨 {persona.current_level}",
            )
        )

    nq = await _gen_question(next_level, asked_count + 1)
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

