import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.db.models import (
    CurriculumItem,
    Exam,
    Persona,
    PersonaMemory,
    Stage,
    StageCurriculumItem,
    Subject,
    TeachingSession,
    WeakPointTag,
)
from app.ai.client import ClaudeClient
from app.ai.prompts import build_practice_answer_eval_prompt, build_practice_prompt, build_socratic_system_prompt, build_teaching_evaluator_prompt
from app.common.weak_points import upsert_weak_point_tag
from app.db.session import AsyncSessionLocal, get_db
from app.deps import get_current_user_id

_claude = ClaudeClient()
from app.exam.router import (
    _assert_exam_unlocked_by_stage,
    _create_regular_exam,
    grade_exam_submission,
    save_user_answers_only,
)
from app.exam.schemas import (
    CreateExamResponse,
    ExamOut,
    ExamQuestionFull,
    GradeResult,
    PersonaAnswerOut,
    SubmitExamRequest,
    SubmitExamResponse,
)
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
from app.teaching.schemas import (
    CreateTeachingSessionRequest,
    CreateTeachingSessionResponse,
    EndSessionResponse,
    MessageRequest,
    TeachingResultResponse,
    UpdatedMemory,
    WeakPointOut,
)

router = APIRouter(prefix="/subjects", tags=["Subjects"])


def _calc_retention(stability: float) -> tuple[float, str]:
    """stability(0~1) → (retention_pct, retention_label)"""
    pct = round(stability * 100, 1)
    if pct >= 80:
        label = "선명"
    elif pct >= 60:
        label = "흐릿해지는 중"
    elif pct >= 40:
        label = "많이 흐릿함"
    elif pct >= 20:
        label = "거의 잊어버림"
    else:
        label = "잊어버림"
    return pct, label


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

    # Persona.current_stage_id → stages.id (no ondelete) 로 인한 FK 위반 방지:
    # 삭제 전에 current_stage_id를 NULL로 만들고, Exam(stage_id FK)도 먼저 삭제
    persona = await db.scalar(select(Persona).where(Persona.subject_id == row.id))
    if persona:
        persona.current_stage_id = None
        exams = (await db.scalars(select(Exam).where(Exam.persona_id == persona.id))).all()
        for exam in exams:
            await db.delete(exam)
        await db.flush()

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
    existing = await db.scalar(select(Persona).where(Persona.subject_id == subject.id))
    if existing:
        raise HTTPException(status_code=409, detail="Persona already exists for this subject")

    # Path param is authoritative for subject binding; reject mismatched body value.
    if payload.subject_id and payload.subject_id != str(subject_id):
        raise HTTPException(status_code=400, detail="subject_id in body must match path subject_id")

    persona = Persona(
        user_id=user_id,
        subject_id=subject.id,
        name=payload.name,
        personality=payload.personality,
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
    persona = await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)
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
    return CreateTeachingSessionResponse(session_id=str(session.id))


@router.post("/{subject_id}/persona/sessions/{session_id}/chat")
async def subject_session_chat(
    subject_id: uuid.UUID,
    session_id: uuid.UUID,
    payload: MessageRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    persona = await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)
    session = await db.scalar(select(TeachingSession).where(TeachingSession.id == session_id, TeachingSession.persona_id == persona.id))
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = list(session.messages or [])
    messages.append({"role": "user", "content": payload.message, "timestamp": datetime.now(timezone.utc).isoformat()})
    session.messages = messages
    flag_modified(session, "messages")  # JSONB mutation 명시적 마킹
    await db.commit()

    # 스트리밍 중 DB 세션 만료를 피하기 위해 필요한 값을 미리 캡처
    session_id_val = session.id
    persona_name = persona.name
    persona_personality = persona.personality
    session_concept = session.concept
    messages_snapshot = list(messages)  # commit 후 만료된 session 대신 로컬 복사본 사용

    # Claude API multi-turn messages 배열 구성 (최근 20턴)
    # messages_snapshot 마지막 항목이 방금 추가한 user 메시지이므로 그대로 사용
    recent = messages_snapshot[-20:]
    api_messages = [
        {"role": m["role"], "content": m["content"]}
        for m in recent
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    # Claude API는 user로 시작 + 마지막이 user여야 함
    # assistant로 시작하는 경우 제거
    while api_messages and api_messages[0]["role"] != "user":
        api_messages.pop(0)
    # 연속된 같은 role 제거 (혹시 저장 실패로 user-user 쌍이 쌓인 경우 대비)
    deduped: list[dict] = []
    for msg in api_messages:
        if deduped and deduped[-1]["role"] == msg["role"]:
            # 같은 role이 연속되면 합치기
            deduped[-1]["content"] += "\n" + msg["content"]
        else:
            deduped.append(dict(msg))
    api_messages = deduped

    system_prompt = build_socratic_system_prompt(
        persona_name=persona_name,
        personality=persona_personality,
        concept=session_concept,
    )

    async def event_gen():
        full_reply = []
        try:
            async for token in _claude.stream_text(
                system_prompt=system_prompt,
                messages=api_messages,
                max_tokens=500,
            ):
                full_reply.append(token)
                yield f"data: {json.dumps({'text': token}, ensure_ascii=False)}\n\n"
        except Exception:
            # Claude API 오류 시 silent 처리 대신 폴백 메시지 전송
            fallback = "잠깐, 다시 한번 설명해줄래요?"
            full_reply.append(fallback)
            yield f"data: {json.dumps({'text': fallback}, ensure_ascii=False)}\n\n"

        # 완성된 응답을 DB에 저장
        # StreamingResponse 반환 후 원래 db 세션이 닫힐 수 있으므로 새 세션 사용
        reply = "".join(full_reply)
        if reply:
            async with AsyncSessionLocal() as fresh_db:
                fresh = await fresh_db.scalar(select(TeachingSession).where(TeachingSession.id == session_id_val))
                if fresh:
                    msgs = list(fresh.messages or [])
                    msgs.append({"role": "assistant", "content": reply, "timestamp": datetime.now(timezone.utc).isoformat()})
                    fresh.messages = msgs
                    flag_modified(fresh, "messages")  # JSONB mutation 명시적 마킹
                    await fresh_db.commit()

        yield "data: {}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.post("/{subject_id}/persona/sessions/{session_id}/end", response_model=EndSessionResponse)
async def subject_session_end(
    subject_id: uuid.UUID,
    session_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> EndSessionResponse:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    persona = await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)
    session = await db.scalar(select(TeachingSession).where(TeachingSession.id == session_id, TeachingSession.persona_id == persona.id))
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    all_msgs = list(session.messages or [])
    user_msgs = [m for m in all_msgs if m.get("role") == "user"]
    total_chars = sum(len(str(m.get("content", ""))) for m in user_msgs)

    # Claude 평가 시도 (haiku 모델로 비용 절감)
    score = 0
    raw_weak: list[str] = []
    try:
        transcript_lines = []
        for m in all_msgs:
            role_label = "선생님" if m.get("role") == "user" else "학생"
            transcript_lines.append(f"{role_label}: {m.get('content', '')}")
        transcript = "\n".join(transcript_lines)
        concept = session.concept or "수학 개념"
        eval_prompt = build_teaching_evaluator_prompt(concept=concept, transcript=transcript)
        raw_eval = await _claude.complete_text(
            system_prompt="너는 수업 평가 전문가야. JSON만 출력해.",
            user_content=eval_prompt,
            max_tokens=400,
            model="claude-haiku-4-5-20251001",
        )
        text = raw_eval.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        eval_data = json.loads(text)
        score = int(eval_data.get("score", 0))
        raw_weak = [str(w) for w in eval_data.get("weak_points", [])][:5]
    except Exception:
        pass

    # Claude 평가 실패 시 문자 수 기반 폴백 (max 90)
    if score == 0:
        score = 90 if total_chars >= 300 else (80 if total_chars >= 180 else (70 if total_chars >= 90 else 60))
    if not raw_weak:
        if len(user_msgs) < 2:
            raw_weak.append("설명 반복 부족")
        if not any("?" in str(m.get("content", "")) for m in user_msgs):
            raw_weak.append("확인 질문 부족")
        if total_chars < 120:
            raw_weak.append("예시 밀도 부족")
        raw_weak = raw_weak[:5]

    session.quality_score = score
    session.weak_points = [{"concept": w, "description": w} for w in raw_weak]
    session.summary_generated = True

    # Upsert PersonaMemory memory for this session's concept
    concept_key = session.concept
    existing_concept = await db.scalar(
        select(PersonaMemory).where(
            PersonaMemory.persona_id == persona.id,
            PersonaMemory.concept == concept_key,
        )
    )
    if existing_concept:
        existing_concept.taught_count += 1
        existing_concept.stability = min(1.0, existing_concept.stability + 0.1)
        existing_concept.last_taught_at = datetime.now(timezone.utc)
        memory_row = existing_concept
    else:
        memory_row = PersonaMemory(
            persona_id=persona.id,
            curriculum_item_id=session.curriculum_item_id,
            concept=concept_key,
            summary=None,
            taught_count=1,
            stability=0.6,
        )
        db.add(memory_row)

    await db.commit()
    await db.refresh(memory_row)

    retention_pct, _ = _calc_retention(memory_row.stability)

    # 완전 기억(stability ≥ 0.9)까지 남은 세션 수 계산 (세션당 +0.1)
    sessions_to_mastery = max(0, int((0.9 - memory_row.stability + 0.09) / 0.1)) if memory_row.stability < 0.9 else 0

    weak_points_out = [WeakPointOut(concept=w, description=w) for w in raw_weak]
    updated_memories = [
        UpdatedMemory(
            concept=memory_row.concept,
            summary=memory_row.summary,
            taught_count=memory_row.taught_count,
            retention=retention_pct,
            sessions_to_mastery=sessions_to_mastery,
        )
    ]

    return EndSessionResponse(
        session_id=str(session.id),
        quality_score=score,
        weak_points=weak_points_out,
        updated_memories=updated_memories,
    )


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
            "created_at": r.created_at.isoformat(),
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
        "created_at": row.created_at.isoformat(),
    }


@router.post("/{subject_id}/persona/weak-points/{tag_id}/practice")
async def get_weak_point_practice(
    subject_id: uuid.UUID,
    tag_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """약점 개념에 대한 Claude 생성 복습 문제·힌트·핵심 개념 설명 반환."""
    subject = await _get_subject(db, subject_id=subject_id, user_id=user_id)
    persona = await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)
    row = await db.scalar(select(WeakPointTag).where(WeakPointTag.id == tag_id, WeakPointTag.persona_id == persona.id))
    if not row:
        raise HTTPException(status_code=404, detail="Weak point tag not found")

    prompt = build_practice_prompt(concept=row.concept, subject_name=subject.name)
    try:
        raw = await _claude.complete_text(
            system_prompt="너는 학생의 약점 개념 복습을 도와주는 전문 교육 AI야. 복습 문제, 힌트, 핵심 개념 설명을 JSON으로만 출력해.",
            user_content=prompt,
            max_tokens=700,
        )
        text = raw.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        data: dict = json.loads(text)
    except Exception:
        data = {
            "problem": f"{row.concept}와 관련된 문제를 선생님이 직접 출제해주세요.",
            "hints": [
                "기본 정의부터 다시 떠올려봐요",
                "간단한 예시로 직접 생각해봐요",
                "선생님께 다시 설명해달라고 해봐요",
            ],
            "concept_title": f"{row.concept} 핵심 정리",
            "concept_explanation": f"{row.concept}은(는) 중요한 개념이에요. 선생님이 다시 한번 설명해주시면 이해할 수 있을 것 같아요!",
        }

    return {
        "concept": row.concept,
        "fail_count": row.fail_count,
        "problem": data.get("problem", ""),
        "hints": data.get("hints", [])[:3],
        "concept_title": data.get("concept_title", f"{row.concept} 핵심 정리"),
        "concept_explanation": data.get("concept_explanation", ""),
    }


@router.post("/{subject_id}/persona/weak-points/{tag_id}/practice/submit")
async def submit_practice_answer(
    subject_id: uuid.UUID,
    tag_id: uuid.UUID,
    payload: dict,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """복습 답변을 Claude로 채점. 정답이면 weak point 삭제 + PersonaMemory retention 갱신."""
    subject = await _get_subject(db, subject_id=subject_id, user_id=user_id)
    persona = await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)
    row = await db.scalar(select(WeakPointTag).where(WeakPointTag.id == tag_id, WeakPointTag.persona_id == persona.id))
    if not row:
        raise HTTPException(status_code=404, detail="Weak point tag not found")

    problem: str = payload.get("problem", "")
    user_answer: str = (payload.get("answer") or "").strip()
    if not user_answer:
        raise HTTPException(status_code=400, detail="answer is required")

    prompt = build_practice_answer_eval_prompt(
        concept=row.concept,
        subject_name=subject.name,
        problem=problem,
        user_answer=user_answer,
    )
    try:
        raw = await _claude.complete_text(
            system_prompt="너는 학생 답변을 평가하는 교육 AI야. JSON만 출력해.",
            user_content=prompt,
            max_tokens=200,
        )
        text = raw.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        result: dict = json.loads(text)
        is_correct: bool = bool(result.get("is_correct", False))
        feedback: str = result.get("feedback", "")
    except Exception:
        # 파싱 실패 시 보수적으로 오답 처리
        is_correct = False
        feedback = "답변을 평가하지 못했어요. 다시 시도해봐요!"

    if is_correct:
        # 1) PersonaMemory retention 갱신 (stability +0.2)
        memory = await db.scalar(
            select(PersonaMemory).where(
                PersonaMemory.persona_id == persona.id,
                PersonaMemory.concept == row.concept,
            )
        )
        if memory:
            memory.stability = min(1.0, memory.stability + 0.2)
            memory.last_taught_at = datetime.now(timezone.utc)
        else:
            db.add(PersonaMemory(
                persona_id=persona.id,
                curriculum_item_id=None,
                concept=row.concept,
                summary=None,
                taught_count=1,
                stability=0.7,
            ))
        # 2) WeakPointTag 삭제
        await db.delete(row)
        await db.commit()

    return {"is_correct": is_correct, "feedback": feedback}


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
            "questions": [
                {
                    "id": q.get("id", ""),
                    "type": q.get("type", ""),
                    "content": q.get("content", ""),
                    "options": q.get("options"),
                    "concept_tag": q.get("concept_tag", ""),
                    "difficulty": q.get("difficulty", 1),
                }
                for q in (r.questions or [])
            ],
            "user_answers": r.user_answers or [],
            "persona_answers": r.persona_answers or [],
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


@router.post("/{subject_id}/persona/exams/{exam_id}/grade", response_model=GradeResult)
async def grade_subject_exam(
    subject_id: uuid.UUID,
    exam_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> GradeResult:
    await _get_subject(db, subject_id=subject_id, user_id=user_id)
    persona = await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)

    exam = await db.scalar(select(Exam).where(Exam.id == exam_id, Exam.persona_id == persona.id))
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    if exam.combined_score is not None:
        raise HTTPException(status_code=409, detail="Exam already graded")

    questions = list(exam.questions or [])
    q_map = {q["id"]: q for q in questions}
    answers_input = list(exam.user_answers or [])
    if not answers_input:
        raise HTTPException(status_code=400, detail="User answers not submitted yet")
    if len(answers_input) != len(questions):
        raise HTTPException(status_code=400, detail="All questions must be answered before grading")

    user_correct = 0
    wrong_concepts: list[str] = []
    user_answers_out: list[dict] = []
    persona_answers_out: list[dict] = []

    for idx, ans in enumerate(answers_input, start=1):
        question_id = ans["question_id"] if isinstance(ans, dict) else ans.question_id
        answer = ans["answer"] if isinstance(ans, dict) else ans.answer
        q = q_map.get(question_id)
        if not q:
            raise HTTPException(status_code=400, detail=f"Question not in exam: {question_id}")
        ok = answer.strip() == str(q.get("answer", "")).strip()
        if ok:
            user_correct += 1
        else:
            concept = str(q.get("concept_tag", "unknown"))
            wrong_concepts.append(concept)
            await upsert_weak_point_tag(db, persona_id=persona.id, concept=concept)
        user_answers_out.append({"question_id": question_id, "answer": answer, "is_correct": ok})
        persona_ok = (idx % 2 == 1)
        persona_answers_out.append({
            "question_id": question_id,
            "thought": "이건 배운 기억이 있어요." if persona_ok else "기억이 좀 흐릿하지만 풀어볼게요.",
            "answer": q.get("answer") if persona_ok else ("1" if str(q.get("answer")) != "1" else "2"),
            "is_correct": persona_ok,
        })

    user_score = int((user_correct / max(len(questions), 1)) * 100)
    persona_score = int((sum(1 for p in persona_answers_out if p["is_correct"]) / max(len(questions), 1)) * 100)
    combined = int((user_score * 0.6) + (persona_score * 0.4))
    pass_threshold = 70
    passed = combined >= pass_threshold

    exam.user_answers = user_answers_out
    exam.persona_answers = persona_answers_out
    exam.user_score = user_score
    exam.persona_score = persona_score
    exam.combined_score = combined
    exam.passed = passed

    # Hide answer keys after grading
    for q in questions:
        q["answer"] = None
    exam.questions = questions

    # Update next_stage_id if passed
    next_stage_id: str | None = None
    if passed:
        stage = await db.scalar(select(Stage).where(Stage.id == exam.stage_id))
        if stage:
            stage.passed = True
            stage.passed_at = datetime.now(timezone.utc)
            next_stage = await db.scalar(
                select(Stage)
                .where(Stage.subject_id == stage.subject_id, Stage.order_index > stage.order_index)
                .order_by(asc(Stage.order_index))
            )
            next_stage_id = str(next_stage.id) if next_stage else None
            if next_stage:
                persona.current_stage_id = next_stage.id

    await db.commit()

    return GradeResult(
        exam_id=str(exam.id),
        user_score=user_score,
        persona_score=persona_score,
        combined_score=combined,
        passed=passed,
        pass_threshold=pass_threshold,
        persona_answers=[
            PersonaAnswerOut(
                question_id=p["question_id"],
                thought=p["thought"],
                answer=str(p["answer"] or ""),
            )
            for p in persona_answers_out
        ],
        wrong_concepts=wrong_concepts,
        next_stage_id=next_stage_id,
    )


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
            select(PersonaMemory)
            .where(PersonaMemory.persona_id == persona.id)
            .order_by(desc(PersonaMemory.last_taught_at))
        )
    ).all()
    result = []
    for r in rows:
        retention_pct, retention_label = _calc_retention(r.stability)
        result.append({
            "id": str(r.id),
            "concept": r.concept,
            "summary": r.summary,
            "taught_count": r.taught_count,
            "stability": r.stability,
            "last_taught_at": r.last_taught_at.isoformat(),
            "retention": retention_pct,
            "retention_label": retention_label,
            "curriculum_item_id": str(r.curriculum_item_id) if r.curriculum_item_id else None,
        })
    return result


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
        select(PersonaMemory).where(PersonaMemory.id == memory_id, PersonaMemory.persona_id == persona.id)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Memory not found")
    retention_pct, retention_label = _calc_retention(row.stability)
    return {
        "id": str(row.id),
        "concept": row.concept,
        "summary": row.summary,
        "taught_count": row.taught_count,
        "stability": row.stability,
        "last_taught_at": row.last_taught_at.isoformat(),
        "retention": retention_pct,
        "retention_label": retention_label,
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
        select(PersonaMemory).where(PersonaMemory.id == memory_id, PersonaMemory.persona_id == persona.id)
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
            "messages": r.messages or [],
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
    persona = await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)
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
    persona = await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)
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


@router.post("/{subject_id}/stages/{stage_id}/exams", response_model=ExamOut)
async def create_stage_exam(
    request: Request,
    subject_id: uuid.UUID,
    stage_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> ExamOut:
    subject = await _get_subject(db, subject_id=subject_id, user_id=user_id)
    stage = await db.scalar(select(Stage).where(Stage.id == stage_id, Stage.subject_id == subject.id))
    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found")

    persona = await _get_subject_persona(db, subject_id=subject_id, user_id=user_id)
    if persona.subject_id and persona.subject_id != subject.id:
        raise HTTPException(status_code=403, detail="Persona is bound to another subject")
    await _assert_exam_unlocked_by_stage(db, persona_id=persona.id, stage_id=stage.id)

    stage_item_ids = (
        await db.scalars(select(StageCurriculumItem.curriculum_item_id).where(StageCurriculumItem.stage_id == stage.id))
    ).all()
    stage_items = (
        await db.scalars(select(CurriculumItem.title).where(CurriculumItem.id.in_(stage_item_ids)))
    ).all() if stage_item_ids else []
    level_hint = max(1, min(9, len(stage_items) or 1))

    create_resp = await _create_regular_exam(
        request=request,
        db=db,
        persona=persona,
        user_id=user_id,
        level=level_hint,
        stage_id=stage.id,
    )

    # Fetch the created exam to return full Exam shape
    exam = await db.scalar(select(Exam).where(Exam.id == uuid.UUID(create_resp.exam_id)))
    if not exam:
        raise HTTPException(status_code=500, detail="Exam creation failed")

    return ExamOut(
        id=str(exam.id),
        stage_id=str(exam.stage_id),
        questions=[
            ExamQuestionFull(
                id=q.get("id", ""),
                type=q.get("type", ""),
                content=q.get("content", ""),
                options=q.get("options"),
                concept_tag=q.get("concept_tag", ""),
                difficulty=q.get("difficulty", 1),
            )
            for q in (exam.questions or [])
        ],
        user_answers=exam.user_answers or [],
        persona_answers=exam.persona_answers or [],
        user_score=exam.user_score,
        persona_score=exam.persona_score,
        combined_score=exam.combined_score,
        passed=exam.passed,
        created_at=exam.created_at.isoformat(),
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

    # overall_retention: average stability across all persona memory concepts
    memory_rows = (
        await db.scalars(select(PersonaMemory).where(PersonaMemory.persona_id == persona.id))
    ).all()
    if memory_rows:
        overall_retention = round(sum(r.stability for r in memory_rows) / len(memory_rows) * 100, 1)
    else:
        overall_retention = 0.0

    # current_stage items with retention
    current_stage_out = None
    if current:
        cur_links = (await db.scalars(select(StageCurriculumItem).where(StageCurriculumItem.stage_id == current.id))).all()
        cur_item_ids = [link.curriculum_item_id for link in cur_links]
        cur_items = (
            await db.scalars(select(CurriculumItem).where(CurriculumItem.id.in_(cur_item_ids)).order_by(CurriculumItem.order_index.asc()))
        ).all() if cur_item_ids else []
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
        concept_map = {r.curriculum_item_id: r for r in memory_rows if r.curriculum_item_id}
        total_count = len(cur_items)
        taught_count = sum(1 for ci in cur_items if ci.id in taught_set)
        untaught_count = max(0, total_count - taught_count)
        items_out = []
        for ci in cur_items:
            mem = concept_map.get(ci.id)
            if mem:
                ret_pct, ret_label = _calc_retention(mem.stability)
            else:
                ret_pct, ret_label = (0.0, "잊어버림")
            items_out.append({
                "id": str(ci.id),
                "title": ci.title,
                "taught": ci.id in taught_set,
                "retention": ret_pct,
                "retention_label": ret_label,
            })
        current_stage_out = {
            "id": str(current.id),
            "name": current.name,
            "order_index": current.order_index,
            "exam_unlocked": (untaught_count == 0 and total_count > 0),
            "untaught_count": untaught_count,
            "items": items_out,
        }

    return {
        "subject": {"id": str(subject.id), "name": subject.name},
        "persona": {"id": str(persona.id), "name": persona.name, "personality": persona.personality},
        "current_stage": current_stage_out,
        "overall_retention": overall_retention,
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


