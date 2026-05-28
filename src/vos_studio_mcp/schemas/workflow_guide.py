"""Schemas for get_workflow_guide tool."""

from pydantic import BaseModel


class WorkflowStep(BaseModel):
    step: int
    tool: str
    purpose: str
    required_inputs: list[str]
    notes: str | None = None


class WorkflowGuideInput(BaseModel):
    goal: str


class WorkflowGuideResponse(BaseModel):
    status: str
    goal: str
    description: str
    steps: list[WorkflowStep]
    total_steps: int
    summary: str
    next_action: str
