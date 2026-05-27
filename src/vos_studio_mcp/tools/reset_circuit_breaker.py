"""reset_circuit_breaker MCP tool — admin tool for manual circuit breaker reset (ADR-0035)."""
from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.auth.context import get_current_client_id
from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.schemas.circuit_breaker import (
    ResetCircuitBreakerInput,
    ResetCircuitBreakerResponse,
)
from vos_studio_mcp.services.circuit_breaker import get_breaker
from vos_studio_mcp.services.providers.capabilities import get_all_provider_ids
from vos_studio_mcp.tools._instrumentation import instrument


def register_reset_circuit_breaker_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    @instrument
    async def reset_circuit_breaker(data: ResetCircuitBreakerInput) -> ResetCircuitBreakerResponse:
        """Manually reset a provider circuit breaker from open/half_open to closed.

        Admin tool: requires authentication. Use when a provider has recovered and
        you want to allow traffic immediately without waiting for the recovery timeout.
        """
        client_id = get_current_client_id()
        if client_id is None:
            raise VosError(ErrorCode.AUTH_REQUIRED, "Authentication required")

        if data.provider not in get_all_provider_ids():
            raise VosError(ErrorCode.INVALID_INPUT, f"Unknown provider: {data.provider}")

        breaker = get_breaker(data.provider)
        previous_state = breaker.state
        previous_failures = breaker.failure_count
        breaker.reset()

        return ResetCircuitBreakerResponse(
            status="reset",
            provider=data.provider,
            previous_state=previous_state,
            previous_failure_count=previous_failures,
            summary=f"Circuit breaker for '{data.provider}' reset from {previous_state} to closed. Failures cleared.",
            next_action="request_api_video",
        )
