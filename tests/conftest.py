import asyncio
from collections.abc import AsyncGenerator

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
async def mcp_session(server_params: StdioServerParameters) -> AsyncGenerator[ClientSession, None]:
    """Live MCP client session for protocol tests.

    Runs the full lifecycle (including teardown) inside a single background
    asyncio Task so anyio cancel scopes are never crossed between tasks.
    """
    session_holder: list[ClientSession] = []
    ready: asyncio.Event = asyncio.Event()
    done: asyncio.Event = asyncio.Event()
    exc_holder: list[BaseException] = []

    async def _lifecycle() -> None:
        try:
            async with (
                stdio_client(server_params) as (read, write),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                session_holder.append(session)
                ready.set()
                await done.wait()
        except Exception as exc:  # noqa: BLE001
            exc_holder.append(exc)
            if not ready.is_set():
                ready.set()

    task: asyncio.Task[None] = asyncio.ensure_future(_lifecycle())
    await ready.wait()

    if exc_holder:
        task.cancel()
        raise exc_holder[0]

    yield session_holder[0]

    done.set()
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
    except (TimeoutError, asyncio.CancelledError):
        task.cancel()
