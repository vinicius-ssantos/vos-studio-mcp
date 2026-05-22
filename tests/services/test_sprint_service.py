"""Unit tests for sprint_service schemas."""

import uuid

import pytest
from pydantic import ValidationError

from vos_studio_mcp.schemas.sprint import BudgetStatus, SprintBudget, SprintInput, SprintResponse


def _make_sprint_input(**overrides):
    defaults = dict(
        client_id=str(uuid.uuid4()),
        brand_kit_id=str(uuid.uuid4()),
        product_name="Summer Campaign",
        campaign_objective="Drive awareness",
        target_audience="Gen Z",
        brief="Create bold summer visuals",
        budget=SprintBudget(max_spend_usd=500.0),
    )
    defaults.update(overrides)
    return SprintInput(**defaults)


def test_sprint_input_budget_must_be_positive():
    with pytest.raises(ValidationError):
        _make_sprint_input(budget=SprintBudget(max_spend_usd=0))


def test_sprint_input_budget_alert_threshold_bounds():
    with pytest.raises(ValidationError):
        _make_sprint_input(budget=SprintBudget(max_spend_usd=100, alert_threshold_pct=1.5))


def test_sprint_input_mode_default():
    data = _make_sprint_input()
    assert data.mode == "dashboard_manual"


def test_sprint_input_mode_api_credits():
    data = _make_sprint_input(mode="api_credits")
    assert data.mode == "api_credits"


def test_budget_status_alert_logic():
    status = BudgetStatus(
        approved_usd=100.0,
        spent_usd=85.0,
        remaining_usd=15.0,
        alert=True,
    )
    assert status.alert is True
    assert status.remaining_usd == 15.0


def test_sprint_response_shape():
    resp = SprintResponse(
        status="created",
        sprint_id="sprint-123",
        summary="Sprint created",
        budget_status=BudgetStatus(
            approved_usd=500.0, spent_usd=0.0, remaining_usd=500.0, alert=False
        ),
        next_action="prepare_dashboard_pack",
    )
    assert resp.budget_status.remaining_usd == 500.0
    assert resp.next_action == "prepare_dashboard_pack"
