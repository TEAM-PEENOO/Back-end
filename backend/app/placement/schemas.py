from pydantic import BaseModel


class PlacementQuestion(BaseModel):
    question_id: str
    question_no: int
    type: str = "multiple_choice"
    content: str
    options: list[str]


class PlacementStartResponse(BaseModel):
    exam_id: str
    current_level: int
    question: PlacementQuestion


class PlacementAnswerRequest(BaseModel):
    exam_id: str
    question_id: str
    answer: str


class PlacementInProgressResponse(BaseModel):
    status: str = "in_progress"
    current_level: int
    next_question: PlacementQuestion


class PlacementResult(BaseModel):
    start_level: int
    known_concepts: list[str]
    weak_concepts: list[str]
    summary: str


class PlacementCompletedResponse(BaseModel):
    status: str = "completed"
    result: PlacementResult

