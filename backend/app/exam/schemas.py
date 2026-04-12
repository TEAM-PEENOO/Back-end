from pydantic import BaseModel


class ExamQuestionOut(BaseModel):
    question_id: str
    question_no: int
    type: str
    content: str
    options: list[str] | None = None


class CreateExamResponse(BaseModel):
    exam_id: str
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
    weak_points_updated: list[str]


class ExamQuestionFull(BaseModel):
    id: str
    type: str
    content: str
    options: list[str] | None = None
    concept_tag: str
    difficulty: int


class ExamOut(BaseModel):
    id: str
    stage_id: str
    questions: list[ExamQuestionFull]
    user_answers: list
    persona_answers: list
    user_score: int | None
    persona_score: int | None
    combined_score: int | None
    passed: bool | None
    created_at: str


class PersonaAnswerOut(BaseModel):
    question_id: str
    thought: str
    answer: str


class GradeResult(BaseModel):
    exam_id: str
    user_score: int
    persona_score: int
    combined_score: int
    passed: bool
    pass_threshold: int
    persona_answers: list[PersonaAnswerOut]
    wrong_concepts: list[str]
    next_stage_id: str | None
