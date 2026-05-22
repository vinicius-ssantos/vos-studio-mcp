"""Unit tests for performance schemas and error types."""

import pytest
from pydantic import ValidationError

from vos_studio_mcp.errors import ErrorCode, VosError  # noqa: E402
from vos_studio_mcp.schemas.performance import PerformanceInput, PerformanceResponse
from vos_studio_mcp.schemas.sprint import CloseSprintInput, CloseSprintResponse

# --- VosError ---

def test_vos_error_stores_error_code():
    err = VosError(ErrorCode.NOT_FOUND, "sprint xyz not found")
    assert err.error_code == ErrorCode.NOT_FOUND
    assert "not_found" in str(err)
    assert "sprint xyz" in str(err)


def test_vos_error_is_exception():
    err = VosError(ErrorCode.SPRINT_CLOSED, "sprint is closed")
    with pytest.raises(VosError, match="sprint is closed"):
        raise err


def test_error_codes_are_strings():
    assert ErrorCode.NOT_FOUND == "not_found"
    assert ErrorCode.SPRINT_CLOSED == "sprint_closed"
    assert ErrorCode.BUDGET_EXCEEDED == "budget_exceeded"
    assert ErrorCode.INVALID_INPUT == "invalid_input"
    assert ErrorCode.PROVIDER_ERROR == "provider_error"


# --- PerformanceInput ---

def test_performance_input_score_bounds():
    with pytest.raises(ValidationError):
        PerformanceInput(asset_id="a", sprint_id="s", score=0)
    with pytest.raises(ValidationError):
        PerformanceInput(asset_id="a", sprint_id="s", score=6)


def test_performance_input_valid():
    data = PerformanceInput(
        asset_id="a1",
        sprint_id="s1",
        score=5,
        label="top_performer",
        hook_label="bold headline",
        angle_label="summer vibes",
    )
    assert data.score == 5
    assert data.label == "top_performer"
    assert data.hook_label == "bold headline"


def test_performance_input_label_default():
    data = PerformanceInput(asset_id="a", sprint_id="s", score=3)
    assert data.label == "neutral"


def test_performance_input_invalid_label():
    with pytest.raises(ValidationError):
        PerformanceInput(asset_id="a", sprint_id="s", score=3, label="unknown")  # type: ignore[arg-type]


def test_performance_response_shape():
    resp = PerformanceResponse(
        status="recorded",
        asset_id="asset-1",
        brand_kit_updated=True,
        summary="Asset recorded as top_performer (score 5/5). Brand kit memory updated.",
        next_action="record_asset_performance",
    )
    assert resp.brand_kit_updated is True
    assert resp.next_action == "record_asset_performance"


# --- CloseSprintInput ---

def test_close_sprint_input_optional_reason():
    data = CloseSprintInput(sprint_id="sprint-1")
    assert data.reason is None


def test_close_sprint_input_with_reason():
    data = CloseSprintInput(sprint_id="sprint-1", reason="campaign ended")
    assert data.reason == "campaign ended"


def test_close_sprint_response_shape():
    resp = CloseSprintResponse(
        status="closed",
        sprint_id="sprint-1",
        sprint_status="closed",
        summary="Sprint closed.",
        next_action="record_asset_performance",
    )
    assert resp.sprint_status == "closed"
    assert resp.next_action == "record_asset_performance"
