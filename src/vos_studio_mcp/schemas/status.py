"""Status response schemas."""

from pydantic import BaseModel, Field


class ServerStatus(BaseModel):
    """Compact status payload for health checks and MCP status tools."""

    status: str = Field(default="ok")
    service: str
    version: str
    environment: str = Field(default="local")
    next_action: str | None = None
