"""Budget and provider quota schemas (ADR-0034)."""

from pydantic import BaseModel, Field


class ProviderUsageSummaryInput(BaseModel):
    """Input for the get_provider_usage_summary tool."""

    provider: str | None = Field(
        default=None,
        description="Filter by provider name (e.g. 'higgsfield'). Omit for all providers.",
    )


class ProviderDailyStats(BaseModel):
    """Today's aggregated spend stats for a single provider."""

    provider: str
    total_estimated_usd: float
    total_actual_usd: float | None
    event_count: int


class ProviderUsageSummaryResponse(BaseModel):
    """Response from get_provider_usage_summary."""

    status: str
    date: str  # ISO 8601 date (today)
    providers: list[ProviderDailyStats]
    total_estimated_usd: float
    daily_limit_usd: float  # 0.0 means not enforced
    remaining_usd: float  # 0.0 when limit not enforced
    limit_enforced: bool
    summary: str
    next_action: str
