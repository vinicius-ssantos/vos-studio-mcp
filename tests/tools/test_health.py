import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_health_check_returns_ok() -> None:
    from src.vos_studio_mcp.tools.health import health_check

    result = await health_check()

    assert result["status"] == "ok"
    assert "server" in result


@pytest.mark.asyncio
async def test_health_check_mcp_protocol(mcp_session) -> None:
    """Layer 4: verifies health_check is discoverable and callable via MCP protocol."""
    result = await mcp_session.call_tool("health_check", {})
    assert result is not None
