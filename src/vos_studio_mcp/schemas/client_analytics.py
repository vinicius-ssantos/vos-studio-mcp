"""Schemas for cross-sprint client performance analytics."""

from pydantic import BaseModel, Field

from vos_studio_mcp.schemas.performance_record import TopPerformer


class ClientPerformanceSummaryResponse(BaseModel):
    status: str
    client_id: str
    period_days: int
    total_sprints: int
    total_records: int
    avg_ctr: float | None = Field(
        default=None, description="Average CTR across all performance records in the period."
    )
    avg_roas: float | None = Field(
        default=None, description="Average ROAS across all performance records in the period."
    )
    top_platform: str | None = Field(
        default=None, description="Platform with the most top-performer records."
    )
    top_performing_assets: list[TopPerformer]
    summary: str
    next_action: str
