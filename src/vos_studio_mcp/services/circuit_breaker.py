"""In-process circuit breaker for external provider calls (Issue #29).

Three states:
  closed   — normal operation; failures accumulate.
  open     — all calls rejected immediately for `recovery_timeout` seconds.
  half_open — one trial call allowed after the timeout; success → closed,
              failure → open again.

The breaker trips on VosError(PROVIDER_ERROR | PROVIDER_TIMEOUT) and on
uncaught network exceptions propagating from adapters.
"""

import logging
import time
from collections.abc import Coroutine
from typing import Any, TypeVar

from vos_studio_mcp.errors import ErrorCode, VosError

log = logging.getLogger(__name__)
T = TypeVar("T")

# Error codes that count as provider failures and should trip the breaker.
_TRIPPABLE: frozenset[ErrorCode] = frozenset(
    {ErrorCode.PROVIDER_ERROR, ErrorCode.PROVIDER_TIMEOUT}
)


def _record_metric(provider: str, operation: str, *, success: bool) -> None:
    """Record a provider call metric.  Lazy import avoids circular dependency."""
    try:
        from vos_studio_mcp.observability.metrics import record_provider_call
        record_provider_call(provider, operation, success=success)
    except Exception:
        pass  # metrics must never affect request path


class CircuitBreaker:
    """Per-provider circuit breaker.

    Not thread-safe; intended for single-process async use.  For multi-worker
    deployments a shared-state store (Redis) would be needed — out of scope
    for the current milestone (YAGNI).
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failures: int = 0
        self._opened_at: float | None = None

    # ------------------------------------------------------------------
    # Public state
    # ------------------------------------------------------------------

    @property
    def state(self) -> str:
        """Return 'closed', 'open', or 'half_open'."""
        if self._opened_at is None:
            return "closed"
        elapsed = time.monotonic() - self._opened_at
        if elapsed >= self.recovery_timeout:
            return "half_open"
        return "open"

    @property
    def failure_count(self) -> int:
        return self._failures

    # ------------------------------------------------------------------
    # Execute a coroutine through the breaker
    # ------------------------------------------------------------------

    async def execute(self, coro: Coroutine[Any, Any, T], operation: str = "call") -> T:
        """Await *coro* if the circuit is closed or half-open.

        Raises VosError(PROVIDER_UNAVAILABLE) immediately if the circuit is open.
        *operation* is used as a label in Prometheus metrics.
        """
        current_state = self.state

        if current_state == "open":
            # The caller already built the coroutine (e.g. provider.call()); close
            # it so it is not left un-awaited (avoids a RuntimeWarning and the
            # resource it may hold).
            coro.close()
            _record_metric(self.name, operation, success=False)
            raise VosError(
                ErrorCode.PROVIDER_UNAVAILABLE,
                f"Provider '{self.name}' is temporarily unavailable "
                f"(circuit open — retry in ~{self.recovery_timeout:.0f}s)",
            )

        try:
            result = await coro
        except VosError as exc:
            if exc.error_code in _TRIPPABLE:
                self._on_failure(current_state)
            _record_metric(self.name, operation, success=False)
            raise
        except Exception:
            # Uncaught network / unexpected errors also trip the breaker.
            self._on_failure(current_state)
            _record_metric(self.name, operation, success=False)
            raise
        else:
            self._on_success()
            _record_metric(self.name, operation, success=True)
            return result

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def _on_success(self) -> None:
        if self._opened_at is not None:
            log.info("circuit_breaker.closed", extra={"breaker_name": self.name})
        self._failures = 0
        self._opened_at = None

    def _on_failure(self, previous_state: str) -> None:
        self._failures += 1
        # Half-open failure immediately re-opens; closed only opens on threshold.
        if previous_state == "half_open" or self._failures >= self.failure_threshold:
            self._opened_at = time.monotonic()
            log.warning(
                "circuit_breaker.opened",
                extra={
                    "breaker_name": self.name,
                    "failures": self._failures,
                    "recovery_timeout_s": self.recovery_timeout,
                },
            )

    # ------------------------------------------------------------------
    # Manual reset (useful in tests and admin tooling)
    # ------------------------------------------------------------------

    def reset(self) -> None:
        self._failures = 0
        self._opened_at = None


# ---------------------------------------------------------------------------
# Global registry
# ---------------------------------------------------------------------------

_registry: dict[str, CircuitBreaker] = {}


def get_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
) -> CircuitBreaker:
    """Return (or lazily create) the named breaker from the global registry."""
    if name not in _registry:
        _registry[name] = CircuitBreaker(name, failure_threshold, recovery_timeout)
    return _registry[name]


def get_all_breakers() -> dict[str, CircuitBreaker]:
    """Return a snapshot of all registered breakers (used by /health endpoint)."""
    return dict(_registry)
