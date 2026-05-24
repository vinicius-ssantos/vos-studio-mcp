"""Unit tests for the circuit breaker (Issue #29)."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.services.circuit_breaker import CircuitBreaker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _success_coro(value: str = "ok") -> AsyncMock:
    m = AsyncMock(return_value=value)
    return m()


def _failing_coro(exc: Exception) -> AsyncMock:
    m = AsyncMock(side_effect=exc)
    return m()


def _provider_error() -> VosError:
    return VosError(ErrorCode.PROVIDER_ERROR, "upstream error")


def _timeout_error() -> VosError:
    return VosError(ErrorCode.PROVIDER_TIMEOUT, "timed out")


def _non_trippable_error() -> VosError:
    return VosError(ErrorCode.INVALID_INPUT, "bad input")


# ---------------------------------------------------------------------------
# Closed state — normal operation
# ---------------------------------------------------------------------------

class TestClosedState:
    @pytest.mark.asyncio
    async def test_successful_call_returns_result(self) -> None:
        breaker = CircuitBreaker("test")
        result = await breaker.execute(_success_coro("hello"))
        assert result == "hello"

    @pytest.mark.asyncio
    async def test_non_trippable_error_does_not_increase_failure_count(self) -> None:
        breaker = CircuitBreaker("test")
        with pytest.raises(VosError):
            await breaker.execute(_failing_coro(_non_trippable_error()))
        assert breaker.failure_count == 0
        assert breaker.state == "closed"

    @pytest.mark.asyncio
    async def test_provider_error_increments_failure_count(self) -> None:
        breaker = CircuitBreaker("test")
        with pytest.raises(VosError):
            await breaker.execute(_failing_coro(_provider_error()))
        assert breaker.failure_count == 1

    @pytest.mark.asyncio
    async def test_success_resets_failure_count(self) -> None:
        breaker = CircuitBreaker("test")
        with pytest.raises(VosError):
            await breaker.execute(_failing_coro(_provider_error()))
        assert breaker.failure_count == 1

        await breaker.execute(_success_coro())
        assert breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_unexpected_exception_trips_breaker(self) -> None:
        breaker = CircuitBreaker("test", failure_threshold=1)
        with pytest.raises(RuntimeError):
            await breaker.execute(_failing_coro(RuntimeError("kaboom")))
        assert breaker.state == "open"


# ---------------------------------------------------------------------------
# Opening the circuit
# ---------------------------------------------------------------------------

class TestOpenState:
    @pytest.mark.asyncio
    async def test_breaker_opens_after_threshold(self) -> None:
        breaker = CircuitBreaker("test", failure_threshold=3)
        for _ in range(3):
            with pytest.raises(VosError):
                await breaker.execute(_failing_coro(_provider_error()))
        assert breaker.state == "open"

    @pytest.mark.asyncio
    async def test_open_breaker_rejects_immediately(self) -> None:
        breaker = CircuitBreaker("test", failure_threshold=1)
        with pytest.raises(VosError):
            await breaker.execute(_failing_coro(_provider_error()))

        with pytest.raises(VosError) as exc_info:
            await breaker.execute(_success_coro())  # should not even run
        assert exc_info.value.error_code == ErrorCode.PROVIDER_UNAVAILABLE

    @pytest.mark.asyncio
    async def test_timeout_error_also_trips_breaker(self) -> None:
        breaker = CircuitBreaker("test", failure_threshold=1)
        with pytest.raises(VosError):
            await breaker.execute(_failing_coro(_timeout_error()))
        assert breaker.state == "open"


# ---------------------------------------------------------------------------
# Half-open state (recovery)
# ---------------------------------------------------------------------------

class TestHalfOpenState:
    @pytest.mark.asyncio
    async def test_breaker_transitions_to_half_open_after_timeout(self) -> None:

        breaker = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.05)
        with pytest.raises(VosError):
            await breaker.execute(_failing_coro(_provider_error()))
        assert breaker.state == "open"

        await asyncio.sleep(0.06)
        assert breaker.state == "half_open"

    @pytest.mark.asyncio
    async def test_success_in_half_open_closes_breaker(self) -> None:
        breaker = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.05)
        with pytest.raises(VosError):
            await breaker.execute(_failing_coro(_provider_error()))

        await asyncio.sleep(0.06)
        result = await breaker.execute(_success_coro("recovered"))
        assert result == "recovered"
        assert breaker.state == "closed"
        assert breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_failure_in_half_open_reopens_breaker(self) -> None:
        breaker = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.05)
        with pytest.raises(VosError):
            await breaker.execute(_failing_coro(_provider_error()))

        await asyncio.sleep(0.06)
        assert breaker.state == "half_open"

        with pytest.raises(VosError):
            await breaker.execute(_failing_coro(_provider_error()))
        assert breaker.state == "open"


# ---------------------------------------------------------------------------
# Manual reset
# ---------------------------------------------------------------------------

class TestReset:
    @pytest.mark.asyncio
    async def test_reset_clears_state(self) -> None:
        breaker = CircuitBreaker("test", failure_threshold=1)
        with pytest.raises(VosError):
            await breaker.execute(_failing_coro(_provider_error()))
        assert breaker.state == "open"

        breaker.reset()
        assert breaker.state == "closed"
        assert breaker.failure_count == 0

        result = await breaker.execute(_success_coro("after reset"))
        assert result == "after reset"
