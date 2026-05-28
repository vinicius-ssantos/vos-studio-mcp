"""Status response schemas."""

from pydantic import BaseModel, Field


class ServerStatus(BaseModel):
    """Compact status payload for health checks and MCP status tools."""

    status: str = Field(default="ok")
    service: str
    version: str
    environment: str = Field(default="local")
    commit_sha: str = Field(default="unknown")
    tool_schema_version: str | None = None
    catalog_fingerprint: str | None = None
    registered_tools_count: int | None = None
    next_action: str | None = None


class ToolSchemaProbeResponse(BaseModel):
    """Compact diagnostic payload for the MCP tool schema exposed to clients."""

    status: str = Field(default="ok")
    tool_name: str
    server_registered: bool
    tool_schema_version: str
    catalog_fingerprint: str
    registered_tools_count: int
    required: list[str] = Field(default_factory=list)
    input_properties: list[str] = Field(default_factory=list)
    uri_supported: bool = False
    mime_type_supported: bool = False
    storage_url_required: bool = False
    advice: str


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
