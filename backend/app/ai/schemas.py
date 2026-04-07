from pydantic import BaseModel, Field


class PlacementQuestionGen(BaseModel):
    content: str
    options: list[str] = Field(min_length=5, max_length=5)
    answer_key: str
    concept_tag: str


class ExamQuestionGen(BaseModel):
    type: str
    content: str
    options: list[str] | None = None
    answer_key: str
    concept_tag: str
    difficulty: int = Field(ge=1, le=3)


class ExamQuestionSetGen(BaseModel):
    questions: list[ExamQuestionGen] = Field(min_length=5, max_length=5)

