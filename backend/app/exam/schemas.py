from pydantic import BaseModel


class ExamQuestionOut(BaseModel):
    question_id: str
    question_no: int
    type: str
    content: str
    options: list[str] | None = None


class CreateExamResponse(BaseModel):
    exam_id: str
    level: int
    questions: list[ExamQuestionOut]


class SubmitExamRequestItem(BaseModel):
    question_id: str
    answer: str


class SubmitExamRequest(BaseModel):
    answers: list[SubmitExamRequestItem]


class SubmitExamResponse(BaseModel):
    user_score: int
    persona_score: int
    combined_score: int
    passed: bool
    level_before: int
    level_after: int
    weak_points_updated: list[str]

