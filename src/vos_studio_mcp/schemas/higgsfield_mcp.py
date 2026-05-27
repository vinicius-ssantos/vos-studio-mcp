"""Schemas for Higgsfield MCP client responses (ADR-0044)."""

from typing import Literal

from pydantic import BaseModel


class McpToolInfo(BaseModel):
    name: str
    description: str | None = None


class McpResourceInfo(BaseModel):
    uri: str
    name: str | None = None
    description: str | None = None


class McpPromptInfo(BaseModel):
    name: str
    description: str | None = None


class HighgsfieldMcpCapabilitiesResponse(BaseModel):
    status: Literal["ok", "disabled", "auth_required", "unreachable"]
    server_name: str | None = None
    server_version: str | None = None
    tools: list[McpToolInfo] = []
    resources: list[McpResourceInfo] = []
    prompts: list[McpPromptInfo] = []
    tool_count: int
    summary: str
    next_action: str
