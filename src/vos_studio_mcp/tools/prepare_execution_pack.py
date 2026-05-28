"""prepare_execution_pack MCP tool — stage-aware operator guidance (Issue #55)."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.schemas.execution_pack import ExecutionPackResponse, PrepareExecutionPackInput
from vos_studio_mcp.services.execution_pack_service import (
    prepare_execution_pack as _prepare_execution_pack,
)
from vos_studio_mcp.tools._instrumentation import instrument


def register_prepare_execution_pack_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    @instrument
    async def prepare_execution_pack(data: PrepareExecutionPackInput) -> ExecutionPackResponse:
        """Prepare a stage-aware execution pack for a VOS production stage.

        Generates structured operator steps, QA criteria, negative constraints,
        and output specifications for the requested asset stage (stage_0 through
        final) and provider.  Returns everything an operator needs to execute
        that stage correctly without deviation.
        """
        return await _prepare_execution_pack(data)
