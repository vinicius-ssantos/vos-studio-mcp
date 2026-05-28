import pytest

from vos_studio_mcp.config.env import Settings
from vos_studio_mcp.services.status import get_server_status


def test_server_status_returns_ok() -> None:
    settings = Settings(MCP_SERVER_NAME="test-mcp")
    result = get_server_status(settings)

    assert result.status == "ok"
    assert result.service == "test-mcp"
    assert result.next_action is not None


@pytest.mark.asyncio
async def test_get_server_status_tool_via_protocol(mcp_session) -> None:
    """Layer 4: verifies get_server_status is callable via MCP protocol."""
    result = await mcp_session.call_tool("get_server_status", {})
    assert result is not None


@pytest.mark.asyncio
async def test_tool_schema_probe_tool_via_protocol(mcp_session) -> None:
    """Layer 4: verifies tool_schema_probe is callable via MCP protocol."""
    result = await mcp_session.call_tool(
        "tool_schema_probe",
        {"tool_name": "register_manual_asset"},
    )
    assert result is not None
