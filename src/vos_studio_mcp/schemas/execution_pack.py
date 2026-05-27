"""Execution pack schemas — stage-aware operator guidance (Issue #55)."""

from typing import Any, Literal

from pydantic import BaseModel, Field

AssetStageParam = Literal["stage_0", "stage_a", "stage_b", "stage_c", "repair", "final"]
ExecutionMode = Literal["dashboard_manual", "api_generated"]


class PrepareExecutionPackInput(BaseModel):
    sprint_id: str = Field(..., description="Sprint to prepare the pack for.")
    asset_stage: AssetStageParam = Field(..., description="VOS production stage to target.")
    provider: str = Field(
        default="manual",
        description="Provider to use: higgsfield, freepik, magnific, or manual.",
    )
    mode: ExecutionMode = Field(
        default="dashboard_manual",
        description="Execution mode: dashboard_manual or api_generated.",
    )
    prompt_version: str = Field(default="v1", description="Prompt version tag.")
    preset_version: str = Field(default="p1", description="Preset version tag.")


class ExecutionStep(BaseModel):
    step_number: int
    action: str
    details: str
    qa_check: str | None = None


class ExecutionPackResponse(BaseModel):
    status: str
    sprint_id: str
    asset_stage: str
    asset_stage_label: str
    provider: str
    mode: str
    objective: str
    operator_steps: list[ExecutionStep]
    qa_criteria: list[str]
    negative_constraints: list[str]
    output_spec: dict[str, Any]
    summary: str
    next_action: str
