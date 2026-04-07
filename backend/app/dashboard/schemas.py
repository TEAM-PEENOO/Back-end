from pydantic import BaseModel


class HomeResponse(BaseModel):
    level: int
    retention_summary: float
    next_goal: str
    recent_session_count: int


class TeachingHistoryItem(BaseModel):
    session_id: str
    concept: str
    quality_score: int | None = None
    created_at: str


class ExamHistoryItem(BaseModel):
    exam_id: str
    exam_type: str
    level: int
    combined_score: int | None = None
    passed: bool | None = None
    created_at: str


class WeakPointItem(BaseModel):
    concept: str
    fail_count: int
    last_failed_at: str

