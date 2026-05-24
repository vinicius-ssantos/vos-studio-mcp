"""Status response schemas."""

from pydantic import BaseModel, Field


class ServerStatus(BaseModel):
    """Compact status payload for health checks and MCP status tools."""

    status: str = Field(default="ok")
    service: str
    version: str
    environment: str = Field(default="local")
    next_action: str | None = None


class ComponentStatus(BaseModel):
    """Health status for a single infrastructure component."""

    status: str  # "ok" | "degraded" | "down"
    latency_ms: float | None = None
    detail: str | None = None


class HealthResponse(BaseModel):
    """Detailed health check response with per-component status."""

    status: str  # "ok" | "degraded" | "down"
    service: str
    version: str
    components: dict[str, ComponentStatus]
