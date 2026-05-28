"""Tests for status service."""

from vos_studio_mcp.config.env import Settings
from vos_studio_mcp.services.status import get_server_status


def test_get_server_status_returns_compact_payload() -> None:
    settings = Settings(MCP_SERVER_NAME="test-mcp")

    result = get_server_status(settings)

    assert result.status == "ok"
    assert result.service == "test-mcp"
    assert result.version
    assert result.commit_sha == "unknown"
    assert result.next_action == "create_client"


def test_get_server_status_includes_tool_catalog_metadata() -> None:
    settings = Settings(MCP_SERVER_NAME="test-mcp")
    tools = []

    result = get_server_status(settings, tools)

    assert result.tool_schema_version
    assert result.catalog_fingerprint
    assert result.registered_tools_count == 0
