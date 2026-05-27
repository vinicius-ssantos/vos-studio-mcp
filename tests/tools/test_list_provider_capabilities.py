"""Unit tests for the list_provider_capabilities MCP tool."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from vos_studio_mcp.tools.list_provider_capabilities import register_provider_capability_tools

# ---------------------------------------------------------------------------
# Helpers — minimal mock MCP
# ---------------------------------------------------------------------------


def _make_mock_mcp() -> tuple[MagicMock, dict[str, Any]]:
    captured: dict[str, Any] = {}
    mock = MagicMock()

    def _tool(**kwargs: Any) -> Any:
        def decorator(fn: Any) -> Any:
            captured[fn.__name__] = fn
            return fn

        return decorator

    mock.tool = _tool
    return mock, captured


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_list_provider_capabilities_is_registered() -> None:
    mock_mcp, captured = _make_mock_mcp()
    register_provider_capability_tools(mock_mcp)  # type: ignore[arg-type]
    assert "list_provider_capabilities" in captured


# ---------------------------------------------------------------------------
# Tool output
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_provider_list() -> None:
    mock_mcp, captured = _make_mock_mcp()
    register_provider_capability_tools(mock_mcp)  # type: ignore[arg-type]

    result = await captured["list_provider_capabilities"](include_disabled=False)

    assert result.total > 0
    assert len(result.providers) == result.total


@pytest.mark.asyncio
async def test_total_matches_enabled_provider_count() -> None:
    from vos_studio_mcp.services.providers.capabilities import list_provider_capabilities

    mock_mcp, captured = _make_mock_mcp()
    register_provider_capability_tools(mock_mcp)  # type: ignore[arg-type]

    result = await captured["list_provider_capabilities"](include_disabled=False)

    expected = len(list_provider_capabilities(include_disabled=False))
    assert result.total == expected
    assert len(result.providers) == expected


@pytest.mark.asyncio
async def test_each_provider_has_required_fields() -> None:
    mock_mcp, captured = _make_mock_mcp()
    register_provider_capability_tools(mock_mcp)  # type: ignore[arg-type]

    result = await captured["list_provider_capabilities"](include_disabled=False)

    for p in result.providers:
        assert p.provider_id, "provider_id must be non-empty"
        assert p.display_name, f"display_name must be non-empty for {p.provider_id}"
        assert isinstance(p.modes, list) and len(p.modes) > 0, (
            f"modes must be non-empty for {p.provider_id}"
        )
        assert isinstance(p.capabilities, list) and len(p.capabilities) > 0, (
            f"capabilities must be non-empty for {p.provider_id}"
        )


@pytest.mark.asyncio
async def test_next_action_set() -> None:
    mock_mcp, captured = _make_mock_mcp()
    register_provider_capability_tools(mock_mcp)  # type: ignore[arg-type]

    result = await captured["list_provider_capabilities"](include_disabled=False)

    assert result.next_action is not None
