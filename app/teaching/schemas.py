from pydantic import BaseModel


class CreateTeachingSessionRequest(BaseModel):
    concept: str


class CreateTeachingSessionResponse(BaseModel):
    session_id: str


class MessageRequest(BaseModel):
    content: str


class OkResponse(BaseModel):
    ok: bool = True


class TeachingResultResponse(BaseModel):
    score: int
    grade_label: str
    weak_points: list[str]
    next_focus: str

