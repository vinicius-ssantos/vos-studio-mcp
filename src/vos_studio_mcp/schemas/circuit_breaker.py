"""Circuit breaker management schemas."""
from pydantic import BaseModel, Field


class ResetCircuitBreakerInput(BaseModel):
    provider: str = Field(description="Provider name to reset: higgsfield, freepik, magnific, cloudflare_workers_ai")


class ResetCircuitBreakerResponse(BaseModel):
    status: str
    provider: str
    previous_state: str
    previous_failure_count: int
    summary: str
    next_action: str
