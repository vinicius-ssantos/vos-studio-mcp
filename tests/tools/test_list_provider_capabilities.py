"""Unit tests for the list_provider_capabilities MCP tool (Issue #44)."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from vos_studio_mcp.schemas.provider import ListProviderCapabilitiesInput

# ---------------------------------------------------------------------------
# Helpers — minimal mock MCP (same pattern as test_tools_layer.py)
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
    from vos_studio_mcp.tools.list_provider_capabilities import (
        register_list_provider_capabilities_tools,
    )

    mock_mcp, captured = _make_mock_mcp()
    register_list_provider_capabilities_tools(mock_mcp)  # type: ignore[arg-type]
    assert "list_provider_capabilities" in captured


# ---------------------------------------------------------------------------
# Tool output — default (enabled_only)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_ok_status() -> None:
    from vos_studio_mcp.tools.list_provider_capabilities import (
        register_list_provider_capabilities_tools,
    )

    mock_mcp, captured = _make_mock_mcp()
    register_list_provider_capabilities_tools(mock_mcp)  # type: ignore[arg-type]

    data = ListProviderCapabilitiesInput(include_disabled=False)
    result = await captured["list_provider_capabilities"](data=data)

    assert result.status == "ok"


@pytest.mark.asyncio
async def test_total_matches_enabled_provider_count() -> None:
    from vos_studio_mcp.services.providers.capability_registry import list_capabilities
    from vos_studio_mcp.tools.list_provider_capabilities import (
        register_list_provider_capabilities_tools,
    )

    mock_mcp, captured = _make_mock_mcp()
    register_list_provider_capabilities_tools(mock_mcp)  # type: ignore[arg-type]

    data = ListProviderCapabilitiesInput(include_disabled=False)
    result = await captured["list_provider_capabilities"](data=data)

    expected = len(list_capabilities(enabled_only=True))
    assert result.total == expected
    assert len(result.providers) == expected


@pytest.mark.asyncio
async def test_include_disabled_returns_more_providers() -> None:
    from vos_studio_mcp.tools.list_provider_capabilities import (
        register_list_provider_capabilities_tools,
    )

    mock_mcp, captured = _make_mock_mcp()
    register_list_provider_capabilities_tools(mock_mcp)  # type: ignore[arg-type]

    enabled_result = await captured["list_provider_capabilities"](
        data=ListProviderCapabilitiesInput(include_disabled=False)
    )
    all_result = await captured["list_provider_capabilities"](
        data=ListProviderCapabilitiesInput(include_disabled=True)
    )

    assert all_result.total > enabled_result.total


@pytest.mark.asyncio
async def test_each_provider_has_required_fields() -> None:
    from vos_studio_mcp.tools.list_provider_capabilities import (
        register_list_provider_capabilities_tools,
    )

    mock_mcp, captured = _make_mock_mcp()
    register_list_provider_capabilities_tools(mock_mcp)  # type: ignore[arg-type]

    data = ListProviderCapabilitiesInput(include_disabled=False)
    result = await captured["list_provider_capabilities"](data=data)

    for p in result.providers:
        assert p.provider_id, f"provider_id must be non-empty for {p}"
        assert p.display_name, f"display_name must be non-empty for {p.provider_id}"
        assert isinstance(p.modes, list) and len(p.modes) > 0, (
            f"modes must be non-empty for {p.provider_id}"
        )
        assert isinstance(p.capabilities, list) and len(p.capabilities) > 0, (
            f"capabilities must be non-empty for {p.provider_id}"
        )


@pytest.mark.asyncio
async def test_next_action_is_prepare_video_blueprint() -> None:
    from vos_studio_mcp.tools.list_provider_capabilities import (
        register_list_provider_capabilities_tools,
    )

    mock_mcp, captured = _make_mock_mcp()
    register_list_provider_capabilities_tools(mock_mcp)  # type: ignore[arg-type]

    data = ListProviderCapabilitiesInput()
    result = await captured["list_provider_capabilities"](data=data)

    assert result.next_action == "prepare_video_blueprint"
