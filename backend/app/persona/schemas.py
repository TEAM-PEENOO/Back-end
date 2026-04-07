from pydantic import BaseModel, Field


class CreatePersonaRequest(BaseModel):
    name: str
    personality: str = Field(pattern="^(curious|careful|clumsy|perfectionist)$")


class UpdatePersonaRequest(BaseModel):
    name: str | None = None
    personality: str | None = Field(default=None, pattern="^(curious|careful|clumsy|perfectionist)$")


class PersonaResponse(BaseModel):
    persona_id: str
    name: str
    personality: str
    current_level: int
    placement_done: bool

