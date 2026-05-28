"""Schemas for check_generation_readiness tool."""

from pydantic import BaseModel


class ReadinessBlocker(BaseModel):
    check: str
    reason: str
    action: str


class GenerationReadinessInput(BaseModel):
    provider: str
    sprint_id: str
    client_id: str


class GenerationReadinessResponse(BaseModel):
    status: str  # "ready" | "blocked"
    provider: str
    sprint_id: str
    ready: bool
    blockers: list[ReadinessBlocker]
    summary: str
    next_action: str
