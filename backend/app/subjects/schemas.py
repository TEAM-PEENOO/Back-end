from pydantic import BaseModel


class SubjectCreateRequest(BaseModel):
    name: str
    description: str | None = None


class SubjectUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class SubjectOut(BaseModel):
    id: str
    name: str
    description: str | None = None
    created_at: str | None = None
    persona: dict | None = None


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
    created_at: str | None = None
    taught: bool | None = None


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
    passed_at: str | None = None
    created_at: str | None = None
    curriculum_items: list[dict] | None = None
    exam_unlocked: bool
    untaught_count: int
