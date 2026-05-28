"""Unit tests for check_generation_readiness service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_SERVICE = "vos_studio_mcp.services.readiness_service"
_SPRINT_ID = "00000000-0000-0000-0000-000000000010"
_CLIENT_ID = "00000000-0000-0000-0000-000000000001"


def _settings(
    *,
    higgsfield_api_key: str = "key",
    higgsfield_mcp_enabled: bool = True,
    higgsfield_mcp_access_token: str = "tok",
) -> MagicMock:
    s = MagicMock()
    s.higgsfield_api_key = higgsfield_api_key
    s.higgsfield_mcp_enabled = higgsfield_mcp_enabled
    s.higgsfield_mcp_access_token = higgsfield_mcp_access_token
    return s


def _mock_sprint(*, status: str = "open", spent: float = 0.0, max_spend: float = 100.0) -> MagicMock:
    sprint = MagicMock()
    sprint.sprint_status = status
    sprint.spent_usd = spent
    sprint.max_spend_usd = max_spend
    sprint.client_id = _CLIENT_ID
    return sprint


def _mock_session(sprint: object) -> MagicMock:
    session = AsyncMock()
    session.get = AsyncMock(return_value=sprint)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


@pytest.mark.asyncio
async def test_ready_when_all_checks_pass() -> None:
    from vos_studio_mcp.services.readiness_service import check_generation_readiness

    sprint = _mock_sprint()
    sprint.client_id = _CLIENT_ID

    with (
        patch(f"{_SERVICE}.get_settings", return_value=_settings()),
        patch(f"{_SERVICE}.get_session", return_value=_mock_session(sprint)),
        patch(f"{_SERVICE}.set_tenant_context", new_callable=AsyncMock),
    ):
        result = await check_generation_readiness("higgsfield", _SPRINT_ID, _CLIENT_ID)

    assert result.ready is True
    assert result.status == "ready"
    assert result.blockers == []
    assert result.next_action == "request_api_video"


@pytest.mark.asyncio
async def test_blocked_when_provider_unknown() -> None:
    from vos_studio_mcp.services.readiness_service import check_generation_readiness

    with patch(f"{_SERVICE}.get_settings", return_value=_settings()):
        result = await check_generation_readiness("unknown_provider", _SPRINT_ID, _CLIENT_ID)

    assert result.ready is False
    assert any(b.check == "provider_known" for b in result.blockers)


@pytest.mark.asyncio
async def test_blocked_when_circuit_breaker_open() -> None:
    from vos_studio_mcp.services.circuit_breaker import get_breaker
    from vos_studio_mcp.services.readiness_service import check_generation_readiness

    breaker = get_breaker("higgsfield_cb_test", failure_threshold=1, recovery_timeout=9999)
    breaker._failures = 5
    breaker._opened_at = 1.0  # force open

    sprint = _mock_sprint()
    sprint.client_id = _CLIENT_ID

    with (
        patch(f"{_SERVICE}.get_settings", return_value=_settings()),
        patch(f"{_SERVICE}.get_breaker", return_value=breaker),
        patch(f"{_SERVICE}.get_session", return_value=_mock_session(sprint)),
        patch(f"{_SERVICE}.set_tenant_context", new_callable=AsyncMock),
    ):
        result = await check_generation_readiness("higgsfield", _SPRINT_ID, _CLIENT_ID)

    assert result.ready is False
    assert any(b.check == "circuit_breaker" for b in result.blockers)


@pytest.mark.asyncio
async def test_blocked_when_higgsfield_mcp_token_missing() -> None:
    from vos_studio_mcp.services.readiness_service import check_generation_readiness

    sprint = _mock_sprint()
    sprint.client_id = _CLIENT_ID

    with (
        patch(f"{_SERVICE}.get_settings", return_value=_settings(higgsfield_mcp_access_token="")),
        patch(f"{_SERVICE}.get_session", return_value=_mock_session(sprint)),
        patch(f"{_SERVICE}.set_tenant_context", new_callable=AsyncMock),
    ):
        result = await check_generation_readiness("higgsfield_mcp", _SPRINT_ID, _CLIENT_ID)

    assert result.ready is False
    assert any(b.check == "provider_token" for b in result.blockers)


@pytest.mark.asyncio
async def test_blocked_when_sprint_closed() -> None:
    from vos_studio_mcp.services.readiness_service import check_generation_readiness

    sprint = _mock_sprint(status="closed")
    sprint.client_id = _CLIENT_ID

    with (
        patch(f"{_SERVICE}.get_settings", return_value=_settings()),
        patch(f"{_SERVICE}.get_session", return_value=_mock_session(sprint)),
        patch(f"{_SERVICE}.set_tenant_context", new_callable=AsyncMock),
    ):
        result = await check_generation_readiness("higgsfield", _SPRINT_ID, _CLIENT_ID)

    assert result.ready is False
    assert any(b.check == "sprint_open" for b in result.blockers)


@pytest.mark.asyncio
async def test_blocked_when_budget_exhausted() -> None:
    from vos_studio_mcp.services.readiness_service import check_generation_readiness

    sprint = _mock_sprint(spent=100.0, max_spend=100.0)
    sprint.client_id = _CLIENT_ID

    with (
        patch(f"{_SERVICE}.get_settings", return_value=_settings()),
        patch(f"{_SERVICE}.get_session", return_value=_mock_session(sprint)),
        patch(f"{_SERVICE}.set_tenant_context", new_callable=AsyncMock),
    ):
        result = await check_generation_readiness("higgsfield", _SPRINT_ID, _CLIENT_ID)

    assert result.ready is False
    assert any(b.check == "sprint_budget" for b in result.blockers)


@pytest.mark.asyncio
async def test_blocked_when_sprint_not_found() -> None:
    from vos_studio_mcp.services.readiness_service import check_generation_readiness

    with (
        patch(f"{_SERVICE}.get_settings", return_value=_settings()),
        patch(f"{_SERVICE}.get_session", return_value=_mock_session(None)),
        patch(f"{_SERVICE}.set_tenant_context", new_callable=AsyncMock),
    ):
        result = await check_generation_readiness("higgsfield", _SPRINT_ID, _CLIENT_ID)

    assert result.ready is False
    assert any(b.check == "sprint_exists" for b in result.blockers)
