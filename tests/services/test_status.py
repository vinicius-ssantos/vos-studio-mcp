"""Tests for status service."""

from vos_studio_mcp.config.env import Settings
from vos_studio_mcp.services.status import get_server_status


def test_get_server_status_returns_compact_payload() -> None:
    settings = Settings(MCP_SERVER_NAME="test-mcp")

    result = get_server_status(settings)

    assert result.status == "ok"
    assert result.service == "test-mcp"
    assert result.version
    assert result.next_action == "create_client"
