import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


@pytest.fixture
def server_params() -> StdioServerParameters:
    """MCP server parameters for protocol-level tests (ADR-0026 Layer 4)."""
    return StdioServerParameters(
        command="uv",
        args=["run", "python", "-m", "vos_studio_mcp.server"],
    )


@pytest.fixture
async def mcp_session(server_params: StdioServerParameters):
    """Live MCP client session for protocol tests."""
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session
