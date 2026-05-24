"""Tool instrumentation helpers — record MCP tool call metrics automatically.

Usage (in a register_* function):

    from vos_studio_mcp.tools._instrumentation import instrument

    @mcp.tool()
    @instrument
    async def my_tool(...): ...

The decorator wraps the async function and calls record_tool_call() with
success/error status after each invocation.  Metrics failures are silently
swallowed so they never affect the tool's response.
"""

import functools
from collections.abc import Callable, Coroutine
from typing import Any

type _AsyncFn[**P, R] = Callable[P, Coroutine[Any, Any, R]]


def instrument[**P, R](fn: _AsyncFn[P, R]) -> _AsyncFn[P, R]:
    """Wrap an async tool function to record Prometheus call metrics."""

    @functools.wraps(fn)
    async def _wrapper(*args: Any, **kwargs: Any) -> Any:
        tool_name = fn.__name__
        try:
            result = await fn(*args, **kwargs)
            _record(tool_name, success=True)
            return result
        except Exception:
            _record(tool_name, success=False)
            raise

    return _wrapper


def _record(tool_name: str, *, success: bool) -> None:
    try:
        from vos_studio_mcp.observability.metrics import record_tool_call
        record_tool_call(tool_name, success=success)
    except Exception:
        pass  # metrics must never affect request path
