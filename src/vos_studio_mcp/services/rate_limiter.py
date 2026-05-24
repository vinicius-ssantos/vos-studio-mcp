"""Sliding-window rate limiter backed by Redis (per client_id per tool).

Algorithm: fixed-window counter with Redis INCR + EXPIRE.
  - Simple, atomic, and correct under concurrent async workers.
  - For the current workload a fixed window is sufficient (KISS).
    A true sliding window (ZADD + ZCOUNT) can be swapped in later if
    needed without changing the public interface.

Usage in a service:

    from vos_studio_mcp.services.rate_limiter import check_rate_limit

    await check_rate_limit("request_api_video", client_id, limit=5, window_seconds=60)
    # raises VosError(RATE_LIMITED) if the client has exceeded the limit

Environment variables
---------------------
RATE_LIMIT_ENABLED  (default: true)
    Set to "false" to disable rate limiting globally (e.g. local dev).
"""

import logging

import redis.asyncio as aioredis

from vos_studio_mcp.config.env import get_settings
from vos_studio_mcp.errors import ErrorCode, VosError

log = logging.getLogger(__name__)

# Default limits per tool (requests / window_seconds).
# Override per call if you need a different limit for a specific operation.
_DEFAULT_LIMITS: dict[str, tuple[int, int]] = {
    "request_api_video":      (10, 60),   # max 10 per minute
    "create_creative_sprint": (20, 60),   # max 20 per minute
    "prepare_dashboard_pack": (30, 60),
    # All other tools fall back to _FALLBACK_LIMIT
}
_FALLBACK_LIMIT: tuple[int, int] = (60, 60)  # 60 req / minute (generous)


async def check_rate_limit(
    tool_name: str,
    client_id: str,
    limit: int | None = None,
    window_seconds: int | None = None,
) -> None:
    """Raise VosError(RATE_LIMITED) if *client_id* has exceeded the limit.

    *limit* and *window_seconds* override the per-tool defaults.
    The check is silently skipped when Redis is unavailable or rate limiting
    is disabled — we prefer availability over strict enforcement.
    """
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return

    default_limit, default_window = _DEFAULT_LIMITS.get(tool_name, _FALLBACK_LIMIT)
    effective_limit = limit if limit is not None else default_limit
    effective_window = window_seconds if window_seconds is not None else default_window

    key = f"rl:{tool_name}:{client_id}"
    try:
        r: aioredis.Redis = aioredis.from_url(  # type: ignore[no-untyped-call]
            settings.redis_url, socket_connect_timeout=1, decode_responses=True
        )
        async with r:
            current = await r.incr(key)
            if current == 1:
                # First request in this window — set TTL
                await r.expire(key, effective_window)
            if current > effective_limit:
                log.warning(
                    "rate_limit.exceeded",
                    extra={
                        "tool": tool_name,
                        "client_id": client_id,
                        "count": current,
                        "limit": effective_limit,
                        "window_s": effective_window,
                    },
                )
                raise VosError(
                    ErrorCode.RATE_LIMITED,
                    f"Rate limit exceeded for '{tool_name}': "
                    f"{effective_limit} requests per {effective_window}s. "
                    f"Retry after the window resets.",
                )
    except VosError:
        raise
    except Exception as exc:
        # Redis unavailable — fail open (don't block the request).
        log.warning("rate_limit.redis_unavailable", extra={"error": str(exc)})
