"""Unit tests for the MCP tools layer.

Each tool is a thin wrapper that delegates to a service. Tests verify:
  - the tool function is registered under the expected name
  - it delegates to the correct service with the correct arguments
  - it returns the service result unchanged

Strategy: a minimal mock MCP captures the decorated function via the
@mcp.tool() decorator without actually starting an MCP server.
"""

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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


def _sprint_id() -> str:
    return str(uuid.uuid4())


def _client_id() -> str:
    return "00000000-0000-0000-0000-000000000001"


# ---------------------------------------------------------------------------
# tools/__init__.py — register_tools
# ---------------------------------------------------------------------------

_EXPECTED_TOOLS = {
    "get_server_status",
    "create_client",
    "save_brand_kit",
    "create_creative_sprint",
    "get_sprint_status",
    "prepare_dashboard_pack",
    "list_sprint_assets",
    "register_manual_asset",
    "close_sprint",
    "record_asset_performance",
    "request_api_video",
    "get_video_job_status",
    "conclude_variant_test",
    "promote_to_library",
    "prepare_video_blueprint",
    "record_performance_metrics",
    "list_video_jobs",
}


def test_register_tools_registers_all_expected_tools() -> None:
    from vos_studio_mcp.tools import register_tools

    mock_mcp, captured = _make_mock_mcp()
    register_tools(mock_mcp)  # type: ignore[arg-type]
    assert set(captured.keys()) == _EXPECTED_TOOLS


# ---------------------------------------------------------------------------
# status.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_server_status_delegates_to_service() -> None:
    from vos_studio_mcp.schemas.status import ServerStatus
    from vos_studio_mcp.tools.status import register_status_tools

    mock_mcp, captured = _make_mock_mcp()
    register_status_tools(mock_mcp)  # type: ignore[arg-type]

    mock_status = ServerStatus(status="ok", service="test", version="0.1.0")

    with (
        patch("vos_studio_mcp.tools.status.get_settings"),
        patch("vos_studio_mcp.tools.status.build_server_status", return_value=mock_status),
    ):
        result = await captured["get_server_status"]()

    assert result is mock_status


# ---------------------------------------------------------------------------
# create_client.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_client_delegates_to_service() -> None:
    from vos_studio_mcp.schemas.client import ClientInput, ClientResponse
    from vos_studio_mcp.tools.create_client import register_create_client_tools

    mock_mcp, captured = _make_mock_mcp()
    register_create_client_tools(mock_mcp)  # type: ignore[arg-type]

    data = ClientInput(name="Acme Corp", industry="Technology")
    mock_resp = ClientResponse(
        status="created",
        client_id=_client_id(),
        name="Acme Corp",
        summary="Client created.",
        next_action="save_brand_kit",
    )

    with patch(
        "vos_studio_mcp.tools.create_client.create_client_service",
        new=AsyncMock(return_value=mock_resp),
    ) as mock_svc:
        result = await captured["create_client"](data=data)

    mock_svc.assert_awaited_once_with(data)
    assert result is mock_resp


# ---------------------------------------------------------------------------
# save_brand_kit.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_brand_kit_delegates_to_service() -> None:
    from vos_studio_mcp.schemas.brand_kit import (
        BrandIdentity,
        BrandKitInput,
        BrandKitResponse,
        BrandRestrictions,
        BrandVisualSystem,
    )
    from vos_studio_mcp.tools.save_brand_kit import register_save_brand_kit_tools

    mock_mcp, captured = _make_mock_mcp()
    register_save_brand_kit_tools(mock_mcp)  # type: ignore[arg-type]

    data = BrandKitInput(
        client_id=_client_id(),
        name="Acme Kit",
        identity=BrandIdentity(brand_name="Acme", target_audience="All", positioning="Value"),
        visual=BrandVisualSystem(),
        restrictions=BrandRestrictions(),
    )
    mock_resp = BrandKitResponse(
        status="created",
        brand_kit_id=str(uuid.uuid4()),
        version="1.0",
        name="Acme Kit",
        summary="Saved.",
        next_action="create_creative_sprint",
    )

    with patch(
        "vos_studio_mcp.tools.save_brand_kit.save_brand_kit_service",
        new=AsyncMock(return_value=mock_resp),
    ) as mock_svc:
        result = await captured["save_brand_kit"](data=data)

    mock_svc.assert_awaited_once_with(data)
    assert result is mock_resp


# ---------------------------------------------------------------------------
# create_creative_sprint.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_creative_sprint_delegates_to_service() -> None:
    from vos_studio_mcp.schemas.sprint import (
        BudgetStatus,
        SprintBudget,
        SprintInput,
        SprintResponse,
    )
    from vos_studio_mcp.tools.create_creative_sprint import register_create_sprint_tools

    mock_mcp, captured = _make_mock_mcp()
    register_create_sprint_tools(mock_mcp)  # type: ignore[arg-type]

    data = SprintInput(
        client_id=_client_id(),
        brand_kit_id=str(uuid.uuid4()),
        product_name="Summer Campaign",
        campaign_objective="Awareness",
        target_audience="Gen Z",
        brief="Bold visuals",
        budget=SprintBudget(max_spend_usd=500.0),
    )
    mock_resp = SprintResponse(
        status="created",
        sprint_id=_sprint_id(),
        summary="Sprint created.",
        budget_status=BudgetStatus(approved_usd=500.0, spent_usd=0.0, remaining_usd=500.0, alert=False),
        next_action="prepare_dashboard_pack",
    )

    with patch(
        "vos_studio_mcp.tools.create_creative_sprint.create_sprint_service",
        new=AsyncMock(return_value=mock_resp),
    ) as mock_svc:
        result = await captured["create_creative_sprint"](data=data)

    mock_svc.assert_awaited_once_with(data)
    assert result is mock_resp


# ---------------------------------------------------------------------------
# get_sprint_status.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_sprint_status_delegates_to_service() -> None:
    from vos_studio_mcp.schemas.sprint import BudgetStatus, SprintStatusResponse
    from vos_studio_mcp.tools.get_sprint_status import register_get_sprint_status_tools

    mock_mcp, captured = _make_mock_mcp()
    register_get_sprint_status_tools(mock_mcp)  # type: ignore[arg-type]

    sid = _sprint_id()
    mock_resp = SprintStatusResponse(
        status="ok",
        sprint_id=sid,
        product_name="Campaign",
        mode="dashboard_manual",
        sprint_status="open",
        budget_status=BudgetStatus(approved_usd=100.0, spent_usd=0.0, remaining_usd=100.0, alert=False),
        asset_count=0,
        summary="Sprint open.",
        next_action="prepare_dashboard_pack",
    )

    with patch(
        "vos_studio_mcp.tools.get_sprint_status.get_status_service",
        new=AsyncMock(return_value=mock_resp),
    ) as mock_svc:
        result = await captured["get_sprint_status"](sprint_id=sid)

    mock_svc.assert_awaited_once_with(sid)
    assert result is mock_resp


# ---------------------------------------------------------------------------
# list_sprint_assets.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_sprint_assets_delegates_to_service() -> None:
    from vos_studio_mcp.schemas.asset import AssetListResponse
    from vos_studio_mcp.tools.list_sprint_assets import register_list_sprint_assets_tools

    mock_mcp, captured = _make_mock_mcp()
    register_list_sprint_assets_tools(mock_mcp)  # type: ignore[arg-type]

    sid = _sprint_id()
    mock_resp = AssetListResponse(status="ok", sprint_id=sid, total=0, assets=[], next_action="prepare_dashboard_pack")

    with patch(
        "vos_studio_mcp.tools.list_sprint_assets.list_service",
        new=AsyncMock(return_value=mock_resp),
    ) as mock_svc:
        result = await captured["list_sprint_assets"](sprint_id=sid)

    mock_svc.assert_awaited_once_with(sid)
    assert result is mock_resp


# ---------------------------------------------------------------------------
# register_manual_asset.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_manual_asset_delegates_to_service() -> None:
    from vos_studio_mcp.schemas.asset import AssetInput, AssetResponse
    from vos_studio_mcp.tools.register_manual_asset import register_manual_asset_tools

    mock_mcp, captured = _make_mock_mcp()
    register_manual_asset_tools(mock_mcp)  # type: ignore[arg-type]

    sid = _sprint_id()
    data = AssetInput(
        sprint_id=sid,
        provider="manual_dashboard",
        prompt_version="v1",
        preset_version="p1",
        storage_url="https://cdn.example.com/img.png",
    )
    mock_resp = AssetResponse(
        status="registered",
        asset_id=str(uuid.uuid4()),
        sprint_id=sid,
        summary="Registered.",
        next_action="register_manual_asset",
    )

    with patch(
        "vos_studio_mcp.tools.register_manual_asset.register_service",
        new=AsyncMock(return_value=mock_resp),
    ) as mock_svc:
        result = await captured["register_manual_asset"](data=data)

    mock_svc.assert_awaited_once_with(data)
    assert result is mock_resp


# ---------------------------------------------------------------------------
# close_sprint.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_sprint_delegates_to_service() -> None:
    from vos_studio_mcp.schemas.sprint import CloseSprintInput, CloseSprintResponse
    from vos_studio_mcp.tools.close_sprint import register_close_sprint_tools

    mock_mcp, captured = _make_mock_mcp()
    register_close_sprint_tools(mock_mcp)  # type: ignore[arg-type]

    data = CloseSprintInput(sprint_id=_sprint_id())
    mock_resp = CloseSprintResponse(
        status="closed",
        sprint_id=data.sprint_id,
        sprint_status="closed",
        summary="Sprint closed.",
        next_action="record_asset_performance",
    )

    with patch(
        "vos_studio_mcp.tools.close_sprint.close_sprint_service",
        new=AsyncMock(return_value=mock_resp),
    ) as mock_svc:
        result = await captured["close_sprint"](data=data)

    mock_svc.assert_awaited_once_with(data)
    assert result is mock_resp


# ---------------------------------------------------------------------------
# record_asset_performance.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_asset_performance_delegates_to_service() -> None:
    from vos_studio_mcp.schemas.performance import PerformanceInput, PerformanceResponse
    from vos_studio_mcp.tools.record_asset_performance import (
        register_record_asset_performance_tools,
    )

    mock_mcp, captured = _make_mock_mcp()
    register_record_asset_performance_tools(mock_mcp)  # type: ignore[arg-type]

    data = PerformanceInput(asset_id=str(uuid.uuid4()), sprint_id=_sprint_id(), score=4, label="top_performer")
    mock_resp = PerformanceResponse(
        status="recorded",
        asset_id=data.asset_id,
        brand_kit_updated=True,
        summary="Recorded.",
        next_action="record_asset_performance",
    )

    with patch(
        "vos_studio_mcp.tools.record_asset_performance.record_service",
        new=AsyncMock(return_value=mock_resp),
    ) as mock_svc:
        result = await captured["record_asset_performance"](data=data)

    mock_svc.assert_awaited_once_with(data)
    assert result is mock_resp


# ---------------------------------------------------------------------------
# request_api_video.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_api_video_delegates_to_service() -> None:
    from vos_studio_mcp.schemas.api_video import ApiVideoInput, ApiVideoResponse
    from vos_studio_mcp.tools.request_api_video import register_request_api_video_tools

    mock_mcp, captured = _make_mock_mcp()
    register_request_api_video_tools(mock_mcp)  # type: ignore[arg-type]

    data = ApiVideoInput(
        sprint_id=_sprint_id(),
        client_id=_client_id(),
        prompt="A cinematic launch",
        prompt_version="v1",
        preset_version="p1",
        approval_token="approved",
    )
    mock_resp = ApiVideoResponse(
        status="queued",
        job_id="gen-123",
        asset_id=str(uuid.uuid4()),
        sprint_id=data.sprint_id,
        estimated_cost_usd=0.06,
        summary="Queued.",
        next_action="get_video_job_status",
    )

    with patch(
        "vos_studio_mcp.tools.request_api_video._service",
        new=AsyncMock(return_value=mock_resp),
    ) as mock_svc:
        result = await captured["request_api_video"](data=data)

    mock_svc.assert_awaited_once_with(data)
    assert result is mock_resp


# ---------------------------------------------------------------------------
# get_video_job_status.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_video_job_status_delegates_to_service() -> None:
    from vos_studio_mcp.schemas.api_video import VideoJobStatusResponse
    from vos_studio_mcp.tools.get_video_job_status import register_get_video_job_status_tools

    mock_mcp, captured = _make_mock_mcp()
    register_get_video_job_status_tools(mock_mcp)  # type: ignore[arg-type]

    asset_id = str(uuid.uuid4())
    mock_resp = VideoJobStatusResponse(
        status="ok",
        asset_id=asset_id,
        generation_status="completed",
        storage_status="stored",
        storage_url="https://cdn.example.com/v.mp4",
        provider_job_id="gen-123",
        summary="Completed.",
        next_action="register_manual_asset",
    )

    with patch(
        "vos_studio_mcp.tools.get_video_job_status._service",
        new=AsyncMock(return_value=mock_resp),
    ) as mock_svc:
        result = await captured["get_video_job_status"](asset_id=asset_id)

    mock_svc.assert_awaited_once_with(asset_id)
    assert result is mock_resp


# ---------------------------------------------------------------------------
# conclude_variant_test.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conclude_variant_test_delegates_to_service() -> None:
    from vos_studio_mcp.schemas.variant import ConcludeVariantTestInput, ConcludeVariantTestResponse
    from vos_studio_mcp.tools.conclude_variant_test import register_conclude_variant_test_tools

    mock_mcp, captured = _make_mock_mcp()
    register_conclude_variant_test_tools(mock_mcp)  # type: ignore[arg-type]

    group_id = str(uuid.uuid4())
    winner_id = str(uuid.uuid4())
    data = ConcludeVariantTestInput(group_id=group_id, winner_variant_id=winner_id, confirmed=True)
    mock_resp = ConcludeVariantTestResponse(
        status="ok",
        group_id=group_id,
        outcome="concluded",
        winner_variant_id=winner_id,
        hypothesis="Bold vs subtle",
        variable="tone",
        variants=[],
        summary="Test concluded.",
        next_action="record_asset_performance",
    )

    with patch(
        "vos_studio_mcp.tools.conclude_variant_test.conclude_variant_test_service",
        new=AsyncMock(return_value=mock_resp),
    ) as mock_svc:
        result = await captured["conclude_variant_test"](data=data)

    mock_svc.assert_awaited_once_with(data)
    assert result is mock_resp


# ---------------------------------------------------------------------------
# promote_to_library.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_promote_to_library_delegates_to_service_with_operator_id() -> None:
    from vos_studio_mcp.schemas.prompt_template import (
        PromoteToLibraryInput,
        PromoteToLibraryResponse,
    )
    from vos_studio_mcp.tools.promote_to_library import register_promote_to_library_tools

    mock_mcp, captured = _make_mock_mcp()
    register_promote_to_library_tools(mock_mcp)  # type: ignore[arg-type]

    data = PromoteToLibraryInput(
        sprint_id=_sprint_id(),
        prompt_version="v2",
        name="Summer Template",
        description="A bold template for summer campaigns",
        prompt_template="A {{product}} ad for {{brand}}",
        confirmed=True,
    )
    mock_resp = PromoteToLibraryResponse(
        status="promoted",
        template_id=str(uuid.uuid4()),
        name="Summer Template",
        performance_tier="experimental",
        summary="Promoted.",
        next_action="create_creative_sprint",
        anonymization_checklist=[],
    )

    with (
        patch(
            "vos_studio_mcp.tools.promote_to_library.get_current_client_id",
            return_value=_client_id(),
        ),
        patch(
            "vos_studio_mcp.tools.promote_to_library.promote_to_library_service",
            new=AsyncMock(return_value=mock_resp),
        ) as mock_svc,
    ):
        result = await captured["promote_to_library"](data=data)

    mock_svc.assert_awaited_once_with(data, _client_id())
    assert result is mock_resp


@pytest.mark.asyncio
async def test_promote_to_library_uses_unknown_when_no_client_id() -> None:
    from vos_studio_mcp.schemas.prompt_template import (
        PromoteToLibraryInput,
        PromoteToLibraryResponse,
    )
    from vos_studio_mcp.tools.promote_to_library import register_promote_to_library_tools

    mock_mcp, captured = _make_mock_mcp()
    register_promote_to_library_tools(mock_mcp)  # type: ignore[arg-type]

    data = PromoteToLibraryInput(
        sprint_id=_sprint_id(),
        prompt_version="v1",
        name="Template",
        description="Template desc",
        prompt_template="A {{product}} ad",
        confirmed=False,
    )
    mock_resp = PromoteToLibraryResponse(
        status="preview",
        template_id=None,
        name="Template",
        performance_tier="experimental",
        summary="Preview.",
        next_action="promote_to_library",
        anonymization_checklist=["Replace brand name"],
    )

    with (
        patch("vos_studio_mcp.tools.promote_to_library.get_current_client_id", return_value=None),
        patch(
            "vos_studio_mcp.tools.promote_to_library.promote_to_library_service",
            new=AsyncMock(return_value=mock_resp),
        ) as mock_svc,
    ):
        result = await captured["promote_to_library"](data=data)

    mock_svc.assert_awaited_once_with(data, "unknown")
    assert result is mock_resp


# ---------------------------------------------------------------------------
# prepare_dashboard_pack.py — has internal logic (sprint open/closed check)
# ---------------------------------------------------------------------------


def _mock_sprint_status(sprint_status: str = "open") -> MagicMock:
    s = MagicMock()
    s.sprint_status = sprint_status
    return s


def _mock_pack() -> MagicMock:
    pack = MagicMock()
    pack.prompt = "A bold summer image"
    pack.provider = "manual_dashboard"
    pack.model = ""
    pack.settings = {}
    pack.checklist = ["Step 1: Generate image"]
    pack.naming_convention = "spr-abc-v1"
    pack.qa_criteria = ["No forbidden elements"]
    pack.negative_prompt = None
    return pack


@pytest.mark.asyncio
async def test_prepare_dashboard_pack_open_sprint_returns_ready() -> None:
    from vos_studio_mcp.schemas.pack import DashboardPackInput
    from vos_studio_mcp.tools.prepare_dashboard_pack import register_prepare_dashboard_pack_tools

    mock_mcp, captured = _make_mock_mcp()
    register_prepare_dashboard_pack_tools(mock_mcp)  # type: ignore[arg-type]

    sid = _sprint_id()
    data = DashboardPackInput(sprint_id=sid, prompt_version="v1", preset_version="p1")

    mock_adapter = MagicMock()
    mock_adapter.prepare_manual_pack = AsyncMock(return_value=_mock_pack())

    with (
        patch(
            "vos_studio_mcp.tools.prepare_dashboard_pack.get_sprint_status",
            new=AsyncMock(return_value=_mock_sprint_status("open")),
        ),
        patch("vos_studio_mcp.tools.prepare_dashboard_pack._adapter", mock_adapter),
    ):
        result = await captured["prepare_dashboard_pack"](data=data)

    assert result.status == "ready"
    assert result.sprint_id == sid
    assert result.next_action == "register_manual_asset"
    assert len(result.checklist) > 0
    mock_adapter.prepare_manual_pack.assert_awaited_once()


@pytest.mark.asyncio
async def test_prepare_dashboard_pack_closed_sprint_returns_blocked() -> None:
    from vos_studio_mcp.schemas.pack import DashboardPackInput
    from vos_studio_mcp.tools.prepare_dashboard_pack import register_prepare_dashboard_pack_tools

    mock_mcp, captured = _make_mock_mcp()
    register_prepare_dashboard_pack_tools(mock_mcp)  # type: ignore[arg-type]

    sid = _sprint_id()
    data = DashboardPackInput(sprint_id=sid, prompt_version="v1", preset_version="p1")

    with patch(
        "vos_studio_mcp.tools.prepare_dashboard_pack.get_sprint_status",
        new=AsyncMock(return_value=_mock_sprint_status("closed")),
    ):
        result = await captured["prepare_dashboard_pack"](data=data)

    assert result.status == "blocked"
    assert result.sprint_id == sid
    assert result.next_action == "sprint_is_closed"


# ---------------------------------------------------------------------------
# prepare_video_blueprint.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prepare_video_blueprint_delegates_to_service() -> None:
    from vos_studio_mcp.schemas.blueprint import VideoBlueprintInput, VideoBlueprintResponse
    from vos_studio_mcp.tools.prepare_video_blueprint import (
        register_prepare_video_blueprint_tools,
    )

    mock_mcp, captured = _make_mock_mcp()
    register_prepare_video_blueprint_tools(mock_mcp)  # type: ignore[arg-type]

    sid = _sprint_id()
    data = VideoBlueprintInput(sprint_id=sid, shot_count=2, provider_targets=["higgsfield"])
    mock_resp = VideoBlueprintResponse(
        status="ready",
        sprint_id=sid,
        creative_intent="Bold video for Gen-Z",
        campaign_objective="Drive trial",
        shot_plan=[],
        negative_prompts=["blurry frames"],
        provider_packs=[],
        manual_checklist=["Review brief"],
        cost_notes="$100 remaining",
        risk_notes="No blocking risks.",
        approval_required=False,
        summary="Blueprint ready: 2 shots, 1 provider.",
        next_action="prepare_dashboard_pack",
    )

    with patch(
        "vos_studio_mcp.tools.prepare_video_blueprint._prepare_video_blueprint",
        new=AsyncMock(return_value=mock_resp),
    ):
        result = await captured["prepare_video_blueprint"](data=data)

    assert result.status == "ready"
    assert result.sprint_id == sid
    assert result.next_action == "prepare_dashboard_pack"


# ---------------------------------------------------------------------------
# record_performance_metrics.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_performance_metrics_delegates_to_service() -> None:
    from vos_studio_mcp.schemas.performance_record import (
        DistributionContext,
        PerformanceMetrics,
        PerformanceRecordInput,
        PerformanceRecordResponse,
    )
    from vos_studio_mcp.tools.record_performance_metrics import (
        register_record_performance_metrics_tools,
    )

    mock_mcp, captured = _make_mock_mcp()
    register_record_performance_metrics_tools(mock_mcp)  # type: ignore[arg-type]

    data = PerformanceRecordInput(
        asset_id=str(uuid.uuid4()),
        distribution=DistributionContext(platform="meta", start_date="2026-05-01"),
        metrics=PerformanceMetrics(impressions=50_000, ctr=0.025, roas=3.2),
        performance_label="top_performer",
    )
    record_id = str(uuid.uuid4())
    mock_resp = PerformanceRecordResponse(
        status="recorded",
        record_id=record_id,
        asset_id=data.asset_id,
        performance_label="top_performer",
        summary="Performance record created.",
        next_action="create_creative_sprint",
    )

    with patch(
        "vos_studio_mcp.tools.record_performance_metrics._create_performance_record",
        new=AsyncMock(return_value=mock_resp),
    ):
        result = await captured["record_performance_metrics"](data=data)

    assert result.status == "recorded"
    assert result.record_id == record_id
    assert result.next_action == "create_creative_sprint"
