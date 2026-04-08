from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from app.db.models import Persona, Subject
from app.db.session import get_db
from app.deps import get_current_user_id
from app.persona.schemas import CreatePersonaRequest, PersonaResponse, UpdatePersonaRequest


router = APIRouter(prefix="/persona", tags=["Persona"])


@router.post("", response_model=PersonaResponse)
async def create_persona(
    payload: CreatePersonaRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> PersonaResponse:
    existing = await db.scalar(select(Persona).where(Persona.user_id == user_id))
    if existing:
        raise HTTPException(status_code=409, detail="Persona already exists for this user")

    subject_id = None
    if payload.subject_id:
        try:
            parsed_subject_id = uuid.UUID(payload.subject_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid subject_id")
        subject = await db.scalar(select(Subject).where(Subject.id == parsed_subject_id, Subject.user_id == user_id))
        if not subject:
            raise HTTPException(status_code=404, detail="Subject not found")
        subject_id = subject.id

    persona = Persona(
        user_id=user_id,
        subject_id=subject_id,
        name=payload.name,
        personality=payload.personality,
        subject="math",
        current_level=1,
        placement_done=False,
    )
    db.add(persona)
    await db.commit()
    await db.refresh(persona)

    return PersonaResponse(
        persona_id=str(persona.id),
        name=persona.name,
        personality=persona.personality,
        subject_id=str(persona.subject_id) if persona.subject_id else None,
        current_stage_id=str(persona.current_stage_id) if persona.current_stage_id else None,
        current_level=persona.current_level,
        placement_done=persona.placement_done,
    )


@router.get("/me", response_model=PersonaResponse)
async def get_me(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> PersonaResponse:
    persona = await db.scalar(select(Persona).where(Persona.user_id == user_id))
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    return PersonaResponse(
        persona_id=str(persona.id),
        name=persona.name,
        personality=persona.personality,
        subject_id=str(persona.subject_id) if persona.subject_id else None,
        current_stage_id=str(persona.current_stage_id) if persona.current_stage_id else None,
        current_level=persona.current_level,
        placement_done=persona.placement_done,
    )


@router.patch("/me", response_model=PersonaResponse)
async def patch_me(
    payload: UpdatePersonaRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> PersonaResponse:
    persona = await db.scalar(select(Persona).where(Persona.user_id == user_id))
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")

    if payload.name is not None:
        persona.name = payload.name
    if payload.personality is not None:
        persona.personality = payload.personality

    await db.commit()
    await db.refresh(persona)
    return PersonaResponse(
        persona_id=str(persona.id),
        name=persona.name,
        personality=persona.personality,
        subject_id=str(persona.subject_id) if persona.subject_id else None,
        current_stage_id=str(persona.current_stage_id) if persona.current_stage_id else None,
        current_level=persona.current_level,
        placement_done=persona.placement_done,
    )

