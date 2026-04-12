import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import ClaudeClient
from app.ai.prompts import build_exam_questions_prompt
from app.common.audit import audit_event
from app.common.rate_limit import rate_limit
from app.common.weak_points import upsert_weak_point_tag
from app.db.models import CurriculumItem, Exam, Persona, StageCurriculumItem, TeachingSession, WeakPointTag
from app.db.session import get_db
from app.deps import get_current_user_id
from app.exam.schemas import CreateExamResponse, ExamQuestionOut, SubmitExamRequest, SubmitExamResponse

_claude = ClaudeClient()

router = APIRouter(prefix="/exams", tags=["Exam"])


async def _get_persona(db: AsyncSession, user_id: str) -> Persona:
    persona = await db.scalar(select(Persona).where(Persona.user_id == user_id))
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    return persona


async def _assert_exam_unlocked_by_stage(
    db: AsyncSession,
    *,
    persona_id: uuid.UUID,
    stage_id: uuid.UUID,
) -> None:
    total = await db.scalar(select(func.count(StageCurriculumItem.stage_id)).where(StageCurriculumItem.stage_id == stage_id))
    taught = await db.scalar(
        select(func.count(func.distinct(TeachingSession.curriculum_item_id)))
        .join(StageCurriculumItem, StageCurriculumItem.curriculum_item_id == TeachingSession.curriculum_item_id)
        .where(StageCurriculumItem.stage_id == stage_id, TeachingSession.persona_id == persona_id)
    )
    total_count = int(total or 0)
    taught_count = int(taught or 0)
    untaught_count = max(0, total_count - taught_count)
    if untaught_count > 0:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "EXAM_LOCKED",
                "message": f"아직 가르치지 않은 항목이 {untaught_count}개 남았어요.",
            },
        )


async def _generate_exam_questions(
    db: AsyncSession,
    *,
    persona_id: uuid.UUID,
    stage_id: uuid.UUID,
    level: int,
    weak_tags: list[str],
) -> list[dict]:
    """Claude API로 실제 시험 문제를 생성한다."""
    # 이 스테이지에서 실제로 가르친 커리큘럼 항목 제목 가져오기
    taught_item_ids = (
        await db.scalars(
            select(TeachingSession.curriculum_item_id)
            .where(
                TeachingSession.persona_id == persona_id,
                TeachingSession.curriculum_item_id.in_(
                    select(StageCurriculumItem.curriculum_item_id).where(StageCurriculumItem.stage_id == stage_id)
                ),
            )
            .distinct()
        )
    ).all()

    taught_titles: list[str] = []
    if taught_item_ids:
        rows = (
            await db.scalars(
                select(CurriculumItem.title).where(CurriculumItem.id.in_(taught_item_ids))
            )
        ).all()
        taught_titles = [t for t in rows if t]

    # Claude API 호출
    prompt = build_exam_questions_prompt(
        level=level,
        taught_concepts=taught_titles,
        weak_tags=weak_tags,
    )
    try:
        raw = await _claude.complete_text(
            system_prompt="너는 한국 수학 교육과정 시험 문제를 JSON으로만 출력하는 전문가야.",
            user_content=prompt,
            max_tokens=1200,
        )
        # JSON 블록 추출 (```json ... ``` 또는 순수 JSON)
        text = raw.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        data = json.loads(text)
        questions_raw: list[dict] = data.get("questions", data) if isinstance(data, dict) else data
    except Exception:
        questions_raw = []

    # 파싱된 문항을 내부 포맷으로 변환
    questions: list[dict] = []
    for i, q in enumerate(questions_raw[:5], start=1):
        qtype = q.get("type", "multiple_choice")
        options = q.get("options") if qtype == "multiple_choice" else None
        answer_key = str(q.get("answer_key", "1"))

        # 객관식: answer_key는 "1"~"5" 인덱스 → 실제 보기 텍스트로 변환
        # 프론트엔드는 보기 텍스트를 그대로 제출하므로 저장값도 텍스트여야 채점이 일치함
        if qtype == "multiple_choice" and options:
            try:
                idx = int(answer_key) - 1
                answer = options[idx] if 0 <= idx < len(options) else answer_key
            except (ValueError, IndexError):
                answer = answer_key
        else:
            answer = answer_key

        questions.append(
            {
                "id": str(uuid.uuid4()),
                "type": qtype,
                "content": q.get("content", ""),
                "options": options,
                "answer": answer,
                "concept_tag": q.get("concept_tag", taught_titles[i - 1] if i <= len(taught_titles) else ""),
                "difficulty": int(q.get("difficulty", 1)),
            }
        )

    # Claude가 5문항 미만을 반환했을 때 부족분 보충
    while len(questions) < 5:
        i = len(questions) + 1
        qtype = "multiple_choice" if i <= 3 else "short_answer"
        fallback_concept = taught_titles[(i - 1) % len(taught_titles)] if taught_titles else weak_tags[(i - 1) % len(weak_tags)] if weak_tags else "수학 개념"
        questions.append(
            {
                "id": str(uuid.uuid4()),
                "type": qtype,
                "content": f"{fallback_concept}에 대한 다음 중 옳은 것은?",
                "options": ["모두 맞다", "모두 틀리다", "알 수 없다", "해당 없음", "정의에 따라 다르다"] if qtype == "multiple_choice" else None,
                "answer": "1" if qtype == "multiple_choice" else fallback_concept,
                "concept_tag": fallback_concept,
                "difficulty": 1 if i <= 2 else (2 if i <= 4 else 3),
            }
        )

    return questions


async def _create_regular_exam(
    *,
    request: Request,
    db: AsyncSession,
    persona: Persona,
    user_id: str,
    level: int,
    stage_id: uuid.UUID | None,
) -> CreateExamResponse:
    if stage_id is None:
        raise HTTPException(status_code=400, detail="stage_id is required")

    weak_rows = (
        await db.scalars(
            select(WeakPointTag.concept)
            .where(WeakPointTag.persona_id == persona.id)
            .order_by(WeakPointTag.fail_count.desc())
        )
    ).all()
    weak_tags = [w for w in weak_rows if w][:10]
    questions = await _generate_exam_questions(
        db,
        persona_id=persona.id,
        stage_id=stage_id,
        level=level,
        weak_tags=weak_tags,
    )

    exam = Exam(
        persona_id=persona.id,
        stage_id=stage_id,
        questions=questions,
        user_answers=[],
        persona_answers=[],
    )
    db.add(exam)
    await db.commit()
    await db.refresh(exam)

    audit_event(
        request=request,
        event="exam.create",
        outcome="success",
        user_id=user_id,
        detail=f"exam_id={exam.id},stage_id={stage_id}",
    )
    out_questions = [
        ExamQuestionOut(
            question_id=q["id"],
            question_no=idx + 1,
            type=q["type"],
            content=q["content"],
            options=q["options"],
        )
        for idx, q in enumerate(questions)
    ]
    return CreateExamResponse(exam_id=str(exam.id), level=level, questions=out_questions)


@router.post("", response_model=CreateExamResponse)
async def create_exam(
    request: Request,
    user_id: str = Depends(get_current_user_id),
    _: None = Depends(rate_limit(limit=20, window_sec=60)),
    db: AsyncSession = Depends(get_db),
) -> CreateExamResponse:
    persona = await _get_persona(db, user_id)
    if not persona.current_stage_id:
        raise HTTPException(status_code=422, detail="No current stage selected")
    await _assert_exam_unlocked_by_stage(db, persona_id=persona.id, stage_id=persona.current_stage_id)
    return await _create_regular_exam(
        request=request,
        db=db,
        persona=persona,
        user_id=user_id,
        level=1,
        stage_id=persona.current_stage_id,
    )


@router.post("/{exam_id}/submit", response_model=SubmitExamResponse)
async def submit_exam(
    request: Request,
    exam_id: uuid.UUID,
    payload: SubmitExamRequest,
    user_id: str = Depends(get_current_user_id),
    _: None = Depends(rate_limit(limit=30, window_sec=60)),
    db: AsyncSession = Depends(get_db),
) -> SubmitExamResponse:
    return await grade_exam_submission(request=request, exam_id=exam_id, payload=payload, user_id=user_id, db=db)


async def save_user_answers_only(
    *,
    exam_id: uuid.UUID,
    payload: SubmitExamRequest,
    user_id: str,
    db: AsyncSession,
) -> None:
    persona = await _get_persona(db, user_id)
    exam = await db.scalar(select(Exam).where(Exam.id == exam_id, Exam.persona_id == persona.id))
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    questions = list(exam.questions or [])
    q_map = {q["id"]: q for q in questions}
    if len(payload.answers) != len(questions):
        raise HTTPException(status_code=400, detail="All questions must be answered")
    user_answers: list[dict] = []
    for item in payload.answers:
        q = q_map.get(item.question_id)
        if not q:
            raise HTTPException(status_code=400, detail=f"Question not in exam: {item.question_id}")
        user_answers.append({"question_id": item.question_id, "answer": item.answer})
    exam.user_answers = user_answers
    await db.commit()


async def grade_exam_submission(
    *,
    request: Request,
    exam_id: uuid.UUID,
    payload: SubmitExamRequest | None,
    user_id: str,
    db: AsyncSession,
) -> SubmitExamResponse:
    persona = await _get_persona(db, user_id)
    exam = await db.scalar(select(Exam).where(Exam.id == exam_id, Exam.persona_id == persona.id))
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    if exam.combined_score is not None:
        raise HTTPException(status_code=409, detail="Exam already submitted")

    questions = list(exam.questions or [])
    q_map = {q["id"]: q for q in questions}
    answers_input = payload.answers if payload is not None else []
    if not answers_input:
        answers_input = [type("Ans", (), a)() for a in (exam.user_answers or [])]
    if len(answers_input) != len(questions):
        raise HTTPException(status_code=400, detail="All questions must be answered before grade")

    user_correct = 0
    weak_points_updated: list[str] = []
    user_answers: list[dict] = []
    persona_answers: list[dict] = []

    for idx, item in enumerate(answers_input, start=1):
        q = q_map.get(item.question_id)
        if not q:
            raise HTTPException(status_code=400, detail=f"Question not in exam: {item.question_id}")
        ok = item.answer.strip() == str(q.get("answer", "")).strip()
        if ok:
            user_correct += 1
        else:
            concept = str(q.get("concept_tag", "unknown"))
            weak_points_updated.append(concept)
            await upsert_weak_point_tag(db, persona_id=persona.id, concept=concept)
        user_answers.append(
            {
                "question_id": item.question_id,
                "answer": item.answer,
                "is_correct": ok,
            }
        )
        persona_ok = (idx % 2 == 1)
        persona_answers.append(
            {
                "question_id": item.question_id,
                "thought": "기억이 좀 흐릿하지만 풀어볼게요." if not persona_ok else "이건 배운 기억이 있어요.",
                "answer": q.get("answer") if persona_ok else ("1" if str(q.get("answer")) != "1" else "2"),
                "is_correct": persona_ok,
            }
        )

    user_score = int((user_correct / max(len(questions), 1)) * 100)
    persona_score = int((sum(1 for p in persona_answers if p["is_correct"]) / max(len(questions), 1)) * 100)
    combined = int((user_score * 0.6) + (persona_score * 0.4))
    passed = combined >= 75 and user_score >= 50 and persona_score >= 30

    exam.user_answers = user_answers
    exam.persona_answers = persona_answers
    exam.user_score = user_score
    exam.persona_score = persona_score
    exam.combined_score = combined
    exam.passed = passed

    # Purge answer keys after grading.
    for q in questions:
        q["answer"] = None
    exam.questions = questions

    # Stage pass update
    if passed:
        persona.current_stage_id = exam.stage_id

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
        level_before=1,
        level_after=1,
        weak_points_updated=weak_points_updated,
    )
