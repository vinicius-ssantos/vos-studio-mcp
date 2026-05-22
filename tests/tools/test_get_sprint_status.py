"""Unit tests for get_sprint_status and list_sprint_assets."""

import uuid

from vos_studio_mcp.schemas.asset import AssetListItem, AssetListResponse
from vos_studio_mcp.schemas.sprint import BudgetStatus, SprintStatusResponse


def _make_budget_status(**kwargs) -> BudgetStatus:
    defaults = dict(approved_usd=500.0, spent_usd=0.0, remaining_usd=500.0, alert=False)
    defaults.update(kwargs)
    return BudgetStatus(**defaults)


def test_sprint_status_response_open_no_alert():
    resp = SprintStatusResponse(
        status="ok",
        sprint_id=str(uuid.uuid4()),
        product_name="Summer Campaign",
        mode="dashboard_manual",
        sprint_status="open",
        budget_status=_make_budget_status(),
        asset_count=0,
        summary="Sprint is open with 0 asset(s) and $500.00 remaining.",
        next_action="prepare_dashboard_pack",
    )
    assert resp.sprint_status == "open"
    assert resp.asset_count == 0
    assert resp.next_action == "prepare_dashboard_pack"


def test_sprint_status_response_alert_when_over_threshold():
    resp = SprintStatusResponse(
        status="ok",
        sprint_id=str(uuid.uuid4()),
        product_name="Summer Campaign",
        mode="dashboard_manual",
        sprint_status="open",
        budget_status=_make_budget_status(spent_usd=420.0, remaining_usd=80.0, alert=True),
        asset_count=5,
        summary="Sprint is open, alert triggered.",
        next_action="review_budget_before_continuing",
    )
    assert resp.budget_status.alert is True
    assert resp.next_action == "review_budget_before_continuing"


def test_asset_list_response_empty():
    resp = AssetListResponse(
        status="ok",
        sprint_id=str(uuid.uuid4()),
        total=0,
        assets=[],
        next_action="prepare_dashboard_pack",
    )
    assert resp.total == 0
    assert resp.assets == []


def test_asset_list_response_with_items():
    sprint_id = str(uuid.uuid4())
    item = AssetListItem(
        asset_id=str(uuid.uuid4()),
        provider="manual_dashboard",
        prompt_version="v1",
        preset_version="p1",
        storage_url="https://cdn.example.com/img.png",
    )
    resp = AssetListResponse(
        status="ok",
        sprint_id=sprint_id,
        total=1,
        assets=[item],
        next_action="prepare_dashboard_pack",
    )
    assert resp.total == 1
    assert resp.assets[0].provider == "manual_dashboard"
    assert resp.assets[0].preview_url is None
