"""Unit tests for the health-check functions in status.py.

Tests cover the error / "down" paths and the overall status aggregation
(ok / degraded / down) that test_status.py doesn't exercise.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vos_studio_mcp.schemas.status import ComponentStatus

_STATUS_MODULE = "vos_studio_mcp.services.status"
_GET_SETTINGS = f"{_STATUS_MODULE}.get_settings"
# _check_database imports get_session locally from services.database
_DATABASE_MODULE = "vos_studio_mcp.services.database"
# get_health imports get_all_breakers locally from services.circuit_breaker
_CIRCUIT_BREAKER_MODULE = "vos_studio_mcp.services.circuit_breaker"


def _mock_settings(server_name: str = "vos-test") -> MagicMock:
    s = MagicMock()
    s.mcp_server_name = server_name
    s.redis_url = "redis://localhost:6379/0"
    return s


# ---------------------------------------------------------------------------
# _check_database
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_database_returns_ok_on_success() -> None:
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch(f"{_DATABASE_MODULE}.get_session", return_value=ctx):
        from vos_studio_mcp.services.status import _check_database

        result = await _check_database()

    assert result.status == "ok"
    assert result.latency_ms is not None


@pytest.mark.asyncio
async def test_check_database_returns_down_on_exception() -> None:
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(side_effect=ConnectionRefusedError("db down"))
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch(f"{_DATABASE_MODULE}.get_session", return_value=ctx):
        from vos_studio_mcp.services.status import _check_database

        result = await _check_database()

    assert result.status == "down"
    assert result.detail == "connection failed"


# ---------------------------------------------------------------------------
# _check_redis
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_redis_returns_ok_on_success() -> None:
    redis_mock = AsyncMock()
    redis_mock.ping = AsyncMock()
    redis_mock.aclose = AsyncMock()

    with patch(_GET_SETTINGS, return_value=_mock_settings()):
        import redis.asyncio as aioredis_real

        with patch.object(aioredis_real, "from_url", return_value=redis_mock):
            from vos_studio_mcp.services.status import _check_redis

            result = await _check_redis()

    assert result.status == "ok"
    redis_mock.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_redis_returns_down_on_exception() -> None:
    redis_mock = AsyncMock()
    redis_mock.ping = AsyncMock(side_effect=ConnectionRefusedError("redis down"))
    redis_mock.aclose = AsyncMock()

    with patch(_GET_SETTINGS, return_value=_mock_settings()):
        import redis.asyncio as aioredis_real

        with patch.object(aioredis_real, "from_url", return_value=redis_mock):
            from vos_studio_mcp.services.status import _check_redis

            result = await _check_redis()

    assert result.status == "down"
    assert result.detail == "ping failed"
    redis_mock.aclose.assert_awaited_once()  # finally block must always run


# ---------------------------------------------------------------------------
# _check_celery_worker
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_celery_worker_returns_ok_when_workers_respond() -> None:
    from vos_studio_mcp.services.status import _check_celery_worker

    with patch(
        f"{_STATUS_MODULE}.asyncio.get_event_loop",
        return_value=MagicMock(
            run_in_executor=AsyncMock(
                return_value={"worker@host1": {"ok": "pong"}, "worker@host2": {"ok": "pong"}}
            )
        ),
    ):
        result = await _check_celery_worker()

    assert result.status == "ok"
    assert "2 workers" in (result.detail or "")


@pytest.mark.asyncio
async def test_check_celery_worker_returns_down_when_no_workers() -> None:
    from vos_studio_mcp.services.status import _check_celery_worker

    with patch(
        f"{_STATUS_MODULE}.asyncio.get_event_loop",
        return_value=MagicMock(
            run_in_executor=AsyncMock(return_value=None)
        ),
    ):
        result = await _check_celery_worker()

    assert result.status == "down"
    assert "no workers" in (result.detail or "")


@pytest.mark.asyncio
async def test_check_celery_worker_returns_down_on_timeout() -> None:
    from vos_studio_mcp.services.status import _check_celery_worker

    with patch(
        f"{_STATUS_MODULE}.asyncio.wait_for",
        side_effect=TimeoutError(),
    ):
        result = await _check_celery_worker()

    assert result.status == "down"
    assert "timed out" in (result.detail or "")


# ---------------------------------------------------------------------------
# get_health — aggregation logic
# ---------------------------------------------------------------------------


def _component_ok() -> ComponentStatus:
    return ComponentStatus(status="ok")


def _component_down() -> ComponentStatus:
    return ComponentStatus(status="down")


@pytest.mark.asyncio
async def test_get_health_overall_ok_when_all_components_up() -> None:
    from vos_studio_mcp.services.status import get_health

    with (
        patch(_GET_SETTINGS, return_value=_mock_settings()),
        patch(f"{_STATUS_MODULE}._check_database", new=AsyncMock(return_value=_component_ok())),
        patch(f"{_STATUS_MODULE}._check_redis", new=AsyncMock(return_value=_component_ok())),
        patch(
            f"{_STATUS_MODULE}._check_celery_worker",
            new=AsyncMock(return_value=_component_ok()),
        ),
        patch(f"{_CIRCUIT_BREAKER_MODULE}.get_all_breakers", return_value={}),
    ):
        result = await get_health()

    assert result.status == "ok"


@pytest.mark.asyncio
async def test_get_health_degraded_when_only_worker_down() -> None:
    from vos_studio_mcp.services.status import get_health

    with (
        patch(_GET_SETTINGS, return_value=_mock_settings()),
        patch(f"{_STATUS_MODULE}._check_database", new=AsyncMock(return_value=_component_ok())),
        patch(f"{_STATUS_MODULE}._check_redis", new=AsyncMock(return_value=_component_ok())),
        patch(
            f"{_STATUS_MODULE}._check_celery_worker",
            new=AsyncMock(return_value=_component_down()),
        ),
        patch(f"{_CIRCUIT_BREAKER_MODULE}.get_all_breakers", return_value={}),
    ):
        result = await get_health()

    assert result.status == "degraded"


@pytest.mark.asyncio
async def test_get_health_down_when_database_down() -> None:
    from vos_studio_mcp.services.status import get_health

    with (
        patch(_GET_SETTINGS, return_value=_mock_settings()),
        patch(
            f"{_STATUS_MODULE}._check_database",
            new=AsyncMock(return_value=_component_down()),
        ),
        patch(f"{_STATUS_MODULE}._check_redis", new=AsyncMock(return_value=_component_ok())),
        patch(
            f"{_STATUS_MODULE}._check_celery_worker",
            new=AsyncMock(return_value=_component_ok()),
        ),
        patch(f"{_CIRCUIT_BREAKER_MODULE}.get_all_breakers", return_value={}),
    ):
        result = await get_health()

    assert result.status == "down"


@pytest.mark.asyncio
async def test_get_health_down_when_redis_down() -> None:
    from vos_studio_mcp.services.status import get_health

    with (
        patch(_GET_SETTINGS, return_value=_mock_settings()),
        patch(f"{_STATUS_MODULE}._check_database", new=AsyncMock(return_value=_component_ok())),
        patch(
            f"{_STATUS_MODULE}._check_redis",
            new=AsyncMock(return_value=_component_down()),
        ),
        patch(
            f"{_STATUS_MODULE}._check_celery_worker",
            new=AsyncMock(return_value=_component_ok()),
        ),
        patch(f"{_CIRCUIT_BREAKER_MODULE}.get_all_breakers", return_value={}),
    ):
        result = await get_health()

    assert result.status == "down"


@pytest.mark.asyncio
async def test_get_health_includes_circuit_breaker_components() -> None:
    """Circuit breaker states must appear in the components dict."""
    from vos_studio_mcp.services.status import get_health

    breaker = MagicMock()
    breaker.state = "open"
    breaker.failure_count = 5

    with (
        patch(_GET_SETTINGS, return_value=_mock_settings()),
        patch(f"{_STATUS_MODULE}._check_database", new=AsyncMock(return_value=_component_ok())),
        patch(f"{_STATUS_MODULE}._check_redis", new=AsyncMock(return_value=_component_ok())),
        patch(
            f"{_STATUS_MODULE}._check_celery_worker",
            new=AsyncMock(return_value=_component_ok()),
        ),
        patch(f"{_CIRCUIT_BREAKER_MODULE}.get_all_breakers", return_value={"higgsfield": breaker}),
    ):
        result = await get_health()

    assert "circuit_breaker.higgsfield" in result.components
    assert result.components["circuit_breaker.higgsfield"].status == "down"
