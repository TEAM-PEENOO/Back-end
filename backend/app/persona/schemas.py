from pydantic import BaseModel, Field


class CreatePersonaRequest(BaseModel):
    name: str
    personality: str = Field(pattern="^(curious|careful|clumsy|perfectionist)$")
    subject_id: str | None = None


class UpdatePersonaRequest(BaseModel):
    name: str | None = None
    personality: str | None = Field(default=None, pattern="^(curious|careful|clumsy|perfectionist)$")


class PersonaResponse(BaseModel):
    persona_id: str
    name: str
    personality: str
    subject_id: str | None = None
    current_stage_id: str | None = None
    current_level: int
    placement_done: bool

