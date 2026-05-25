"""Tool-layer tests for reset_circuit_breaker (ADR-0035)."""

from unittest.mock import MagicMock, patch

import pytest

from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.schemas.circuit_breaker import ResetCircuitBreakerInput

_CLIENT_ID = "aaaaaaaa-0000-0000-0000-aaaaaaaaaaaa"
_PATCH_AUTH = "vos_studio_mcp.tools.reset_circuit_breaker.get_current_client_id"


def _make_mock_mcp():
    captured: dict = {}
    mock_mcp = MagicMock()

    def _tool(**kwargs):
        def decorator(fn):
            captured[fn.__name__] = fn
            return fn
        return decorator

    mock_mcp.tool = _tool
    return mock_mcp, captured


@pytest.mark.asyncio
async def test_auth_required_when_no_client_id() -> None:
    from vos_studio_mcp.tools.reset_circuit_breaker import register_reset_circuit_breaker_tools

    mock_mcp, captured = _make_mock_mcp()
    register_reset_circuit_breaker_tools(mock_mcp)

    with patch(_PATCH_AUTH, return_value=None), pytest.raises(VosError) as exc_info:
        await captured["reset_circuit_breaker"](data=ResetCircuitBreakerInput(provider="higgsfield"))

    assert exc_info.value.error_code == ErrorCode.AUTH_REQUIRED


@pytest.mark.asyncio
async def test_invalid_input_for_unknown_provider() -> None:
    from vos_studio_mcp.tools.reset_circuit_breaker import register_reset_circuit_breaker_tools

    mock_mcp, captured = _make_mock_mcp()
    register_reset_circuit_breaker_tools(mock_mcp)

    with patch(_PATCH_AUTH, return_value=_CLIENT_ID), pytest.raises(VosError) as exc_info:
        await captured["reset_circuit_breaker"](data=ResetCircuitBreakerInput(provider="unknown_provider"))

    assert exc_info.value.error_code == ErrorCode.INVALID_INPUT


@pytest.mark.asyncio
async def test_resets_closed_breaker_stays_closed() -> None:
    from vos_studio_mcp.services.circuit_breaker import CircuitBreaker, _registry
    from vos_studio_mcp.tools.reset_circuit_breaker import register_reset_circuit_breaker_tools

    # Install a fresh closed breaker in the registry
    _registry["higgsfield"] = CircuitBreaker("higgsfield")
    assert _registry["higgsfield"].state == "closed"

    mock_mcp, captured = _make_mock_mcp()
    register_reset_circuit_breaker_tools(mock_mcp)

    with patch(_PATCH_AUTH, return_value=_CLIENT_ID):
        result = await captured["reset_circuit_breaker"](data=ResetCircuitBreakerInput(provider="higgsfield"))

    assert result.status == "reset"
    assert result.previous_state == "closed"
    assert result.previous_failure_count == 0
    assert _registry["higgsfield"].state == "closed"


@pytest.mark.asyncio
async def test_resets_open_breaker_to_closed() -> None:
    import time

    from vos_studio_mcp.services.circuit_breaker import CircuitBreaker, _registry
    from vos_studio_mcp.tools.reset_circuit_breaker import register_reset_circuit_breaker_tools

    # Trip the breaker open (opened_at must be recent so recovery_timeout hasn't elapsed)
    breaker = CircuitBreaker("freepik", failure_threshold=1, recovery_timeout=3600.0)
    breaker._failures = 2
    breaker._opened_at = time.monotonic()  # opened just now — still open
    _registry["freepik"] = breaker
    assert breaker.state == "open"

    mock_mcp, captured = _make_mock_mcp()
    register_reset_circuit_breaker_tools(mock_mcp)

    with patch(_PATCH_AUTH, return_value=_CLIENT_ID):
        result = await captured["reset_circuit_breaker"](data=ResetCircuitBreakerInput(provider="freepik"))

    assert result.status == "reset"
    assert result.previous_state == "open"
    assert result.previous_failure_count == 2
    assert _registry["freepik"].state == "closed"
    assert _registry["freepik"].failure_count == 0


@pytest.mark.asyncio
async def test_summary_contains_provider_name() -> None:
    from vos_studio_mcp.services.circuit_breaker import CircuitBreaker, _registry
    from vos_studio_mcp.tools.reset_circuit_breaker import register_reset_circuit_breaker_tools

    _registry["magnific"] = CircuitBreaker("magnific")

    mock_mcp, captured = _make_mock_mcp()
    register_reset_circuit_breaker_tools(mock_mcp)

    with patch(_PATCH_AUTH, return_value=_CLIENT_ID):
        result = await captured["reset_circuit_breaker"](data=ResetCircuitBreakerInput(provider="magnific"))

    assert "magnific" in result.summary
    assert result.provider == "magnific"


@pytest.mark.asyncio
async def test_next_action_is_request_api_video() -> None:
    from vos_studio_mcp.services.circuit_breaker import CircuitBreaker, _registry
    from vos_studio_mcp.tools.reset_circuit_breaker import register_reset_circuit_breaker_tools

    _registry["higgsfield"] = CircuitBreaker("higgsfield")

    mock_mcp, captured = _make_mock_mcp()
    register_reset_circuit_breaker_tools(mock_mcp)

    with patch(_PATCH_AUTH, return_value=_CLIENT_ID):
        result = await captured["reset_circuit_breaker"](data=ResetCircuitBreakerInput(provider="higgsfield"))

    assert result.next_action == "request_api_video"
