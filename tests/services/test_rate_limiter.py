"""Unit tests for Redis-backed rate limiter."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.services.rate_limiter import check_rate_limit

_SETTINGS = "vos_studio_mcp.services.rate_limiter.get_settings"
_REDIS = "vos_studio_mcp.services.rate_limiter.aioredis"

_CLIENT_ID = "00000000-0000-0000-0000-000000000001"


def _mock_settings(enabled: bool = True) -> MagicMock:
    s = MagicMock()
    s.rate_limit_enabled = enabled
    s.redis_url = "redis://localhost:6379/0"
    return s


def _mock_redis(current_count: int = 1) -> MagicMock:
    """Return a mock aioredis module with a configured client."""
    r = AsyncMock()
    r.incr = AsyncMock(return_value=current_count)
    r.expire = AsyncMock()
    r.__aenter__ = AsyncMock(return_value=r)
    r.__aexit__ = AsyncMock(return_value=False)

    module = MagicMock()
    module.from_url = MagicMock(return_value=r)
    return module, r


class TestRateLimiterDisabled:
    @pytest.mark.asyncio
    async def test_skips_check_when_disabled(self) -> None:
        settings = _mock_settings(enabled=False)
        with patch(_SETTINGS, return_value=settings):
            # Must not raise and must not touch Redis
            await check_rate_limit("request_api_video", _CLIENT_ID)

    @pytest.mark.asyncio
    async def test_disabled_even_if_redis_unavailable(self) -> None:
        settings = _mock_settings(enabled=False)
        with patch(_SETTINGS, return_value=settings):
            # Should silently pass without any Redis interaction
            await check_rate_limit("request_api_video", _CLIENT_ID, limit=0)


class TestRateLimiterAllowed:
    @pytest.mark.asyncio
    async def test_allows_request_under_limit(self) -> None:
        settings = _mock_settings()
        module, redis_client = _mock_redis(current_count=5)
        with patch(_SETTINGS, return_value=settings), patch(_REDIS, module):
            await check_rate_limit("request_api_video", _CLIENT_ID, limit=10, window_seconds=60)

    @pytest.mark.asyncio
    async def test_sets_ttl_on_first_request(self) -> None:
        settings = _mock_settings()
        module, redis_client = _mock_redis(current_count=1)
        with patch(_SETTINGS, return_value=settings), patch(_REDIS, module):
            await check_rate_limit("request_api_video", _CLIENT_ID, limit=10, window_seconds=30)

        redis_client.expire.assert_awaited_once_with(
            f"rl:request_api_video:{_CLIENT_ID}", 30
        )

    @pytest.mark.asyncio
    async def test_does_not_set_ttl_on_subsequent_requests(self) -> None:
        settings = _mock_settings()
        module, redis_client = _mock_redis(current_count=5)
        with patch(_SETTINGS, return_value=settings), patch(_REDIS, module):
            await check_rate_limit("request_api_video", _CLIENT_ID, limit=10, window_seconds=60)

        redis_client.expire.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_uses_correct_redis_key(self) -> None:
        settings = _mock_settings()
        module, redis_client = _mock_redis(current_count=1)
        with patch(_SETTINGS, return_value=settings), patch(_REDIS, module):
            await check_rate_limit("my_tool", _CLIENT_ID, limit=10, window_seconds=60)

        redis_client.incr.assert_awaited_once_with(f"rl:my_tool:{_CLIENT_ID}")


class TestRateLimiterExceeded:
    @pytest.mark.asyncio
    async def test_raises_rate_limited_when_over_limit(self) -> None:
        settings = _mock_settings()
        module, _ = _mock_redis(current_count=11)
        with patch(_SETTINGS, return_value=settings), patch(_REDIS, module):
            with pytest.raises(VosError) as exc_info:
                await check_rate_limit("request_api_video", _CLIENT_ID, limit=10, window_seconds=60)

        assert exc_info.value.error_code == ErrorCode.RATE_LIMITED

    @pytest.mark.asyncio
    async def test_error_message_includes_tool_and_limit(self) -> None:
        settings = _mock_settings()
        module, _ = _mock_redis(current_count=100)
        with patch(_SETTINGS, return_value=settings), patch(_REDIS, module):
            with pytest.raises(VosError) as exc_info:
                await check_rate_limit("request_api_video", _CLIENT_ID, limit=5, window_seconds=30)

        msg = exc_info.value.message
        assert "request_api_video" in msg
        assert "5" in msg
        assert "30" in msg

    @pytest.mark.asyncio
    async def test_exactly_at_limit_is_allowed(self) -> None:
        """count == limit should pass; only count > limit is rejected."""
        settings = _mock_settings()
        module, _ = _mock_redis(current_count=10)
        with patch(_SETTINGS, return_value=settings), patch(_REDIS, module):
            await check_rate_limit("request_api_video", _CLIENT_ID, limit=10, window_seconds=60)


class TestRateLimiterFailOpen:
    @pytest.mark.asyncio
    async def test_fails_open_when_redis_unavailable(self) -> None:
        """If Redis is down, requests should pass through (availability > strict enforcement)."""
        settings = _mock_settings()
        module = MagicMock()
        module.from_url = MagicMock(side_effect=ConnectionRefusedError("Redis down"))
        with patch(_SETTINGS, return_value=settings), patch(_REDIS, module):
            # Must NOT raise
            await check_rate_limit("request_api_video", _CLIENT_ID, limit=1, window_seconds=60)

    @pytest.mark.asyncio
    async def test_fails_open_on_redis_error_during_incr(self) -> None:
        settings = _mock_settings()
        r = AsyncMock()
        r.incr = AsyncMock(side_effect=Exception("timeout"))
        r.__aenter__ = AsyncMock(return_value=r)
        r.__aexit__ = AsyncMock(return_value=False)
        module = MagicMock()
        module.from_url = MagicMock(return_value=r)
        with patch(_SETTINGS, return_value=settings), patch(_REDIS, module):
            await check_rate_limit("request_api_video", _CLIENT_ID, limit=1, window_seconds=60)


class TestDefaultLimits:
    @pytest.mark.asyncio
    async def test_uses_per_tool_default_limit(self) -> None:
        """request_api_video default is 10/60 — count=10 should pass."""
        settings = _mock_settings()
        module, _ = _mock_redis(current_count=10)
        with patch(_SETTINGS, return_value=settings), patch(_REDIS, module):
            await check_rate_limit("request_api_video", _CLIENT_ID)

    @pytest.mark.asyncio
    async def test_uses_fallback_limit_for_unknown_tool(self) -> None:
        """Unknown tools get the generous fallback (60/60) — count=60 passes."""
        settings = _mock_settings()
        module, _ = _mock_redis(current_count=60)
        with patch(_SETTINGS, return_value=settings), patch(_REDIS, module):
            await check_rate_limit("unknown_tool", _CLIENT_ID)

    @pytest.mark.asyncio
    async def test_fallback_exceeded_at_61(self) -> None:
        settings = _mock_settings()
        module, _ = _mock_redis(current_count=61)
        with patch(_SETTINGS, return_value=settings), patch(_REDIS, module):
            with pytest.raises(VosError) as exc_info:
                await check_rate_limit("unknown_tool", _CLIENT_ID)
        assert exc_info.value.error_code == ErrorCode.RATE_LIMITED
