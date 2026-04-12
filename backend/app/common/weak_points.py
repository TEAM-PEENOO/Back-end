from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PersonaMemory, WeakPointTag


async def upsert_weak_point_tag(db: AsyncSession, *, persona_id, concept: str) -> None:
    existing = await db.scalar(
        select(WeakPointTag).where(WeakPointTag.persona_id == persona_id, WeakPointTag.concept == concept)
    )
    if existing:
        existing.fail_count += 1
        existing.last_failed_at = datetime.now(timezone.utc)
    else:
        db.add(
            WeakPointTag(
                persona_id=persona_id,
                concept=concept,
                fail_count=1,
                last_failed_at=datetime.now(timezone.utc),
            )
        )

    # 시험에서 틀린 개념은 PersonaMemory stability 감소 (약점 반영)
    memory = await db.scalar(
        select(PersonaMemory).where(PersonaMemory.persona_id == persona_id, PersonaMemory.concept == concept)
    )
    if memory:
        memory.stability = max(0.0, memory.stability - 0.1)
