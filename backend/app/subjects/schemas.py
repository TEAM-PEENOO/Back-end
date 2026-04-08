from pydantic import BaseModel


class SubjectCreateRequest(BaseModel):
    name: str
    description: str | None = None


class SubjectOut(BaseModel):
    id: str
    name: str
    description: str | None = None


class CurriculumCreateRequest(BaseModel):
    title: str
    note: str | None = None
    order_index: int | None = None


class CurriculumOut(BaseModel):
    id: str
    subject_id: str
    title: str
    note: str | None = None
    order_index: int


class StageCreateRequest(BaseModel):
    name: str
    order_index: int | None = None
    curriculum_item_ids: list[str] = []


class StageOut(BaseModel):
    id: str
    subject_id: str
    name: str
    order_index: int
    passed: bool
    exam_unlocked: bool
    untaught_count: int
