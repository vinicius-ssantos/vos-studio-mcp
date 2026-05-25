"""Unit tests for the get_provider_usage_summary MCP tool (ADR-0034, Issue #42)."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.schemas.budget import ProviderDailyStats, ProviderUsageSummaryInput

_GET_CLIENT = "vos_studio_mcp.tools.get_provider_usage_summary.get_current_client_id"
_GET_SETTINGS = "vos_studio_mcp.tools.get_provider_usage_summary.get_settings"
_GET_SUMMARY = "vos_studio_mcp.tools.get_provider_usage_summary.get_provider_daily_summary"

_CLIENT_ID = "aaaaaaaa-0000-0000-0000-000000000001"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_mcp() -> tuple[MagicMock, dict[str, Any]]:
    """Return (mock_mcp, captured) where captured maps name → async fn."""
    captured: dict[str, Any] = {}
    mock = MagicMock()

    def _tool(**kwargs: Any) -> Any:
        def decorator(fn: Any) -> Any:
            captured[fn.__name__] = fn
            return fn

        return decorator

    mock.tool = _tool
    return mock, captured


def _settings(daily_limit: float = 0.0) -> MagicMock:
    s = MagicMock()
    s.provider_daily_limit_usd = daily_limit
    return s


def _stats(provider: str = "higgsfield", estimated: float = 0.5) -> list[ProviderDailyStats]:
    return [
        ProviderDailyStats(
            provider=provider,
            total_estimated_usd=estimated,
            total_actual_usd=None,
            event_count=5,
        )
    ]


async def _call_tool(
    data: ProviderUsageSummaryInput | None = None,
    client_id: str | None = _CLIENT_ID,
    daily_limit: float = 0.0,
    stats: list[ProviderDailyStats] | None = None,
) -> Any:
    """Helper: register the tool on a mock MCP and call the inner function."""
    from vos_studio_mcp.tools.get_provider_usage_summary import (
        register_get_provider_usage_summary_tools,
    )

    mock_mcp, captured = _make_mock_mcp()
    register_get_provider_usage_summary_tools(mock_mcp)  # type: ignore[arg-type]

    tool_fn = captured["get_provider_usage_summary"]
    input_data = data or ProviderUsageSummaryInput()
    stats_to_use = stats if stats is not None else []

    with (
        patch(_GET_CLIENT, return_value=client_id),
        patch(_GET_SETTINGS, return_value=_settings(daily_limit=daily_limit)),
        patch(_GET_SUMMARY, new_callable=AsyncMock, return_value=stats_to_use),
    ):
        return await tool_fn(input_data)


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_raises_auth_required_when_no_client_id() -> None:
    with pytest.raises(VosError) as exc_info:
        await _call_tool(client_id=None)
    assert exc_info.value.error_code == ErrorCode.AUTH_REQUIRED


# ---------------------------------------------------------------------------
# No limit enforced
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_limit_returns_ok_status() -> None:
    result = await _call_tool(daily_limit=0.0, stats=_stats(estimated=0.3))
    assert result.status == "ok"
    assert result.limit_enforced is False
    assert result.remaining_usd == 0.0
    assert result.daily_limit_usd == 0.0
    assert "no daily limit" in result.summary


@pytest.mark.asyncio
async def test_no_limit_next_action_is_request_api_video() -> None:
    result = await _call_tool(daily_limit=0.0, stats=_stats(estimated=0.3))
    assert result.next_action == "request_api_video"


# ---------------------------------------------------------------------------
# With limit enforced
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_within_limit_reports_remaining() -> None:
    result = await _call_tool(daily_limit=1.0, stats=_stats(estimated=0.3))
    assert result.limit_enforced is True
    assert abs(result.remaining_usd - 0.7) < 1e-9
    assert "0.30" in result.summary
    assert "1.00" in result.summary
    assert "0.70" in result.summary


@pytest.mark.asyncio
async def test_within_limit_next_action_is_request_api_video() -> None:
    result = await _call_tool(daily_limit=1.0, stats=_stats(estimated=0.5))
    assert result.next_action == "request_api_video"


@pytest.mark.asyncio
async def test_quota_exhausted_next_action() -> None:
    # Remaining = 0 when spend equals or exceeds limit
    result = await _call_tool(daily_limit=1.0, stats=_stats(estimated=1.0))
    assert result.remaining_usd == 0.0
    assert result.next_action == "quota_exhausted"


# ---------------------------------------------------------------------------
# Empty stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_stats_returns_zero_totals() -> None:
    result = await _call_tool(daily_limit=1.0, stats=[])
    assert result.total_estimated_usd == 0.0
    assert result.providers == []
    assert "No provider usage" in result.summary


# ---------------------------------------------------------------------------
# Response fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_response_includes_today_date() -> None:
    import datetime

    result = await _call_tool(stats=_stats())
    # Should be a valid ISO date
    datetime.date.fromisoformat(result.date)


@pytest.mark.asyncio
async def test_response_includes_provider_stats() -> None:
    stats = [
        ProviderDailyStats(
            provider="higgsfield",
            total_estimated_usd=0.5,
            total_actual_usd=0.45,
            event_count=3,
        ),
        ProviderDailyStats(
            provider="freepik",
            total_estimated_usd=0.2,
            total_actual_usd=None,
            event_count=1,
        ),
    ]
    result = await _call_tool(stats=stats)
    assert len(result.providers) == 2
    providers = {s.provider for s in result.providers}
    assert "higgsfield" in providers
    assert "freepik" in providers


@pytest.mark.asyncio
async def test_total_estimated_sums_all_providers() -> None:
    stats = [
        ProviderDailyStats(
            provider="higgsfield", total_estimated_usd=0.5, total_actual_usd=None, event_count=2
        ),
        ProviderDailyStats(
            provider="freepik", total_estimated_usd=0.3, total_actual_usd=None, event_count=1
        ),
    ]
    result = await _call_tool(stats=stats)
    assert abs(result.total_estimated_usd - 0.8) < 1e-9
