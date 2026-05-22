"""Dashboard pack schemas."""

from pydantic import BaseModel, Field


class DashboardPackInput(BaseModel):
    sprint_id: str
    prompt_version: str = Field(..., min_length=1)
    preset_version: str = Field(..., min_length=1)


class DashboardPackResponse(BaseModel):
    status: str
    sprint_id: str
    prompt: str
    provider: str
    model: str
    settings: dict[str, object]
    checklist: list[str]
    naming_convention: str
    qa_criteria: list[str]
    negative_prompt: str | None = None
    next_action: str
