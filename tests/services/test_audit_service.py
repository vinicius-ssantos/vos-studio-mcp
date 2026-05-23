"""Unit tests for audit_service.emit_audit_event (ADR-0015)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vos_studio_mcp.services.audit_service import (
    AuditAction,
    AuditResult,
    emit_audit_event,
)

_MODULE = "vos_studio_mcp.services.audit_service"


def _make_session_ctx() -> MagicMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_writes_audit_log_to_db() -> None:
    ctx = _make_session_ctx()

    with (
        patch(f"{_MODULE}.get_session", return_value=ctx),
        patch(f"{_MODULE}.bypass_rls", new_callable=AsyncMock),
        patch(f"{_MODULE}.get_current_client_id", return_value="client-001"),
    ):
        await emit_audit_event(
            action=AuditAction.SPRINT_CREATED,
            entity_type="sprint",
            entity_id=str(uuid.uuid4()),
            result=AuditResult.SUCCESS,
        )

    session = ctx.__aenter__.return_value
    session.add.assert_called_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_emit_uses_provided_actor_over_context() -> None:
    ctx = _make_session_ctx()
    added_event = None

    def _capture(obj: object) -> None:
        nonlocal added_event
        added_event = obj

    ctx.__aenter__.return_value.add = _capture

    with (
        patch(f"{_MODULE}.get_session", return_value=ctx),
        patch(f"{_MODULE}.bypass_rls", new_callable=AsyncMock),
        patch(f"{_MODULE}.get_current_client_id", return_value="ctx-client"),
    ):
        await emit_audit_event(
            action=AuditAction.API_VIDEO_REQUESTED,
            entity_type="asset",
            entity_id="asset-1",
            actor="explicit-client",
            result=AuditResult.SUCCESS,
        )

    assert added_event is not None
    assert added_event.actor == "explicit-client"


@pytest.mark.asyncio
async def test_emit_falls_back_to_system_when_no_client_id() -> None:
    ctx = _make_session_ctx()
    added_event = None

    def _capture(obj: object) -> None:
        nonlocal added_event
        added_event = obj

    ctx.__aenter__.return_value.add = _capture

    with (
        patch(f"{_MODULE}.get_session", return_value=ctx),
        patch(f"{_MODULE}.bypass_rls", new_callable=AsyncMock),
        patch(f"{_MODULE}.get_current_client_id", return_value=None),
    ):
        await emit_audit_event(
            action=AuditAction.UPLOAD_COMPLETED,
            entity_type="asset",
            entity_id="asset-1",
            result=AuditResult.SUCCESS,
        )

    assert added_event is not None
    assert added_event.actor == "system"


@pytest.mark.asyncio
async def test_emit_stores_all_fields() -> None:
    ctx = _make_session_ctx()
    added_event = None

    def _capture(obj: object) -> None:
        nonlocal added_event
        added_event = obj

    ctx.__aenter__.return_value.add = _capture

    with (
        patch(f"{_MODULE}.get_session", return_value=ctx),
        patch(f"{_MODULE}.bypass_rls", new_callable=AsyncMock),
        patch(f"{_MODULE}.get_current_client_id", return_value=None),
    ):
        await emit_audit_event(
            action=AuditAction.API_VIDEO_REQUESTED,
            entity_type="asset",
            entity_id="eid-001",
            actor="client-abc",
            provider="higgsfield",
            mode="api_credits",
            cost_estimate_usd=0.35,
            approval_status="approved",
            result=AuditResult.SUCCESS,
            failure_reason=None,
        )

    assert added_event is not None
    assert added_event.action == AuditAction.API_VIDEO_REQUESTED
    assert added_event.entity_type == "asset"
    assert added_event.entity_id == "eid-001"
    assert added_event.provider == "higgsfield"
    assert added_event.mode == "api_credits"
    assert added_event.cost_estimate_usd == pytest.approx(0.35)
    assert added_event.approval_status == "approved"
    assert added_event.result == AuditResult.SUCCESS
    assert added_event.failure_reason is None


# ---------------------------------------------------------------------------
# Failure resilience — must never raise
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_swallows_db_error_and_logs_warning() -> None:
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("db connection lost"))
    ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(f"{_MODULE}.get_session", return_value=ctx),
        patch(f"{_MODULE}.get_current_client_id", return_value=None),
        patch(f"{_MODULE}.log") as mock_log,
    ):
        # Must not raise
        await emit_audit_event(
            action=AuditAction.UPLOAD_FAILED,
            entity_type="asset",
            entity_id="asset-x",
            result=AuditResult.FAILED,
            failure_reason="timeout",
        )

    mock_log.warning.assert_called_once()
    call_kwargs = mock_log.warning.call_args
    assert "audit_event_write_failed" in call_kwargs[0]


@pytest.mark.asyncio
async def test_emit_swallows_commit_error() -> None:
    ctx = _make_session_ctx()
    ctx.__aenter__.return_value.commit = AsyncMock(side_effect=OSError("disk full"))

    with (
        patch(f"{_MODULE}.get_session", return_value=ctx),
        patch(f"{_MODULE}.bypass_rls", new_callable=AsyncMock),
        patch(f"{_MODULE}.get_current_client_id", return_value=None),
    ):
        # Must not raise
        await emit_audit_event(
            action=AuditAction.SPRINT_CLOSED,
            entity_type="sprint",
            entity_id="sprint-x",
            result=AuditResult.SUCCESS,
        )


# ---------------------------------------------------------------------------
# AuditAction constants are non-empty strings
# ---------------------------------------------------------------------------


def test_audit_action_constants_are_strings() -> None:
    for attr in vars(AuditAction):
        if attr.startswith("_"):
            continue
        value = getattr(AuditAction, attr)
        assert isinstance(value, str) and value, f"AuditAction.{attr} should be a non-empty string"


def test_audit_result_constants_are_strings() -> None:
    for attr in vars(AuditResult):
        if attr.startswith("_"):
            continue
        value = getattr(AuditResult, attr)
        assert isinstance(value, str) and value, f"AuditResult.{attr} should be a non-empty string"
