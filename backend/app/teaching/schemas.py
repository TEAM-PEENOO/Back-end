from pydantic import BaseModel


class CreateTeachingSessionRequest(BaseModel):
    concept: str
    curriculum_item_id: str | None = None


class CreateTeachingSessionResponse(BaseModel):
    session_id: str


class MessageRequest(BaseModel):
    message: str


class OkResponse(BaseModel):
    ok: bool = True


class WeakPointOut(BaseModel):
    concept: str
    description: str


class UpdatedMemory(BaseModel):
    concept: str
    summary: str | None
    taught_count: int
    retention: float


class EndSessionResponse(BaseModel):
    session_id: str
    quality_score: int
    weak_points: list[WeakPointOut]
    updated_memories: list[UpdatedMemory]


class TeachingResultResponse(BaseModel):
    score: int
    grade_label: str
    weak_points: list[str]
    next_focus: str
