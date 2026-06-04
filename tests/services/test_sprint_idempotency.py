"""Unit tests for create_creative_sprint idempotency key (Issue #34)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vos_studio_mcp.schemas.sprint import SprintBudget, SprintInput, SprintResponse

_SERVICE = "vos_studio_mcp.services.sprint_service"
_GUARD = f"{_SERVICE}.assert_owns_client"
_GET_SESSION = f"{_SERVICE}.get_session"
_SET_TENANT = f"{_SERVICE}.set_tenant_context"
_FIND_IDEM = f"{_SERVICE}._find_idempotent_sprint"
_GET_LIBRARY = f"{_SERVICE}.get_library_suggestions"
_GET_PERFORMERS = f"{_SERVICE}.get_top_performers"

_CLIENT_ID = "00000000-0000-0000-0000-000000000001"
_BRAND_KIT_ID = "00000000-0000-0000-0000-000000000002"
_IDEMPOTENCY_KEY = "my-campaign-2026-q2"


def _minimal_input(idempotency_key: str | None = None) -> SprintInput:
    return SprintInput(
        client_id=_CLIENT_ID,
        brand_kit_id=_BRAND_KIT_ID,
        product_name="Widget Pro",
        campaign_objective="awareness",
        target_audience="gen-z",
        brief="Launch campaign",
        budget=SprintBudget(max_spend_usd=100.0),
        idempotency_key=idempotency_key,
    )


def _mock_existing_sprint() -> MagicMock:
    s = MagicMock()
    s.id = "aaaaaaaa-0000-0000-0000-000000000003"
    s.product_name = "Widget Pro"
    s.mode = "dashboard_manual"
    s.max_spend_usd = 100.0
    s.spent_usd = 0.0
    s.alert_threshold_pct = 0.8
    s.idempotency_key = _IDEMPOTENCY_KEY
    return s


def _session_ctx() -> MagicMock:
    session = AsyncMock()
    session.get = AsyncMock(return_value=MagicMock(performance_memory={}))
    session.add = MagicMock()  # SQLAlchemy Session.add is synchronous

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


class TestSprintIdempotencyKey:
    @pytest.mark.asyncio
    async def test_no_key_creates_sprint_normally(self) -> None:
        """When no idempotency_key is supplied the sprint is created fresh."""
        from vos_studio_mcp.services.sprint_service import create_creative_sprint

        new_sprint = MagicMock()
        new_sprint.id = "bbbbbbbb-0000-0000-0000-000000000004"
        new_sprint.product_name = "Widget Pro"
        new_sprint.mode = "dashboard_manual"
        new_sprint.max_spend_usd = 100.0
        new_sprint.spent_usd = 0.0
        new_sprint.alert_threshold_pct = 0.8

        ctx = _session_ctx()
        with (
            patch(_GUARD),
            patch(_GET_SESSION, return_value=ctx),
            patch(_SET_TENANT),
            patch(_GET_LIBRARY, new=AsyncMock(return_value=[])),
            patch(_GET_PERFORMERS, new=AsyncMock(return_value=[])),
        ):
            session = await ctx.__aenter__()
            session.get.return_value = MagicMock(performance_memory={})
            session.flush = AsyncMock()
            session.commit = AsyncMock()
            session.refresh = AsyncMock()

            # Patch Sprint constructor to return our mock
            with patch(f"{_SERVICE}.Sprint", return_value=new_sprint):
                resp = await create_creative_sprint(_minimal_input())

        assert resp.idempotency_key is None

    @pytest.mark.asyncio
    async def test_key_with_existing_sprint_returns_existing(self) -> None:
        """When idempotency_key matches an existing sprint, return it without creating."""
        from vos_studio_mcp.services.sprint_service import create_creative_sprint

        existing = _mock_existing_sprint()
        ctx = _session_ctx()

        with (
            patch(_GUARD),
            patch(_GET_SESSION, return_value=ctx),
            patch(_SET_TENANT),
            patch(_FIND_IDEM, new=AsyncMock(return_value=existing)),
        ):
            resp = await create_creative_sprint(_minimal_input(idempotency_key=_IDEMPOTENCY_KEY))

        assert resp.status == "created"
        assert resp.sprint_id == str(existing.id)
        assert resp.idempotency_key == _IDEMPOTENCY_KEY
        assert "Idempotent replay" in resp.summary

    @pytest.mark.asyncio
    async def test_key_with_no_existing_sprint_creates_new(self) -> None:
        """When idempotency_key is new (no match), a fresh sprint is created."""
        from vos_studio_mcp.services.sprint_service import create_creative_sprint

        new_sprint = MagicMock()
        new_sprint.id = "cccccccc-0000-0000-0000-000000000005"
        new_sprint.product_name = "Widget Pro"
        new_sprint.mode = "dashboard_manual"
        new_sprint.max_spend_usd = 100.0
        new_sprint.spent_usd = 0.0
        new_sprint.alert_threshold_pct = 0.8

        ctx = _session_ctx()

        with (
            patch(_GUARD),
            patch(_GET_SESSION, return_value=ctx),
            patch(_SET_TENANT),
            patch(_FIND_IDEM, new=AsyncMock(return_value=None)),
            patch(_GET_LIBRARY, new=AsyncMock(return_value=[])),
            patch(_GET_PERFORMERS, new=AsyncMock(return_value=[])),
        ):
            session = await ctx.__aenter__()
            session.flush = AsyncMock()
            session.commit = AsyncMock()
            session.refresh = AsyncMock()

            with patch(f"{_SERVICE}.Sprint", return_value=new_sprint):
                resp = await create_creative_sprint(
                    _minimal_input(idempotency_key=_IDEMPOTENCY_KEY)
                )

        assert resp.idempotency_key == _IDEMPOTENCY_KEY
        assert "Idempotent replay" not in resp.summary

    @pytest.mark.asyncio
    async def test_idempotent_replay_does_not_call_audit_service(self) -> None:
        """Replays must not emit a SPRINT_CREATED audit event."""
        from vos_studio_mcp.services.sprint_service import create_creative_sprint

        existing = _mock_existing_sprint()
        ctx = _session_ctx()

        with (
            patch(_GUARD),
            patch(_GET_SESSION, return_value=ctx),
            patch(_SET_TENANT),
            patch(_FIND_IDEM, new=AsyncMock(return_value=existing)),
            patch(f"{_SERVICE}.emit_audit_event") as mock_audit,
        ):
            await create_creative_sprint(_minimal_input(idempotency_key=_IDEMPOTENCY_KEY))

        mock_audit.assert_not_called()


class TestSprintInputSchema:
    def test_idempotency_key_is_optional(self) -> None:
        data = _minimal_input()
        assert data.idempotency_key is None

    def test_idempotency_key_max_length_128(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            _minimal_input(idempotency_key="x" * 129)

    def test_idempotency_key_stored_in_response(self) -> None:
        from vos_studio_mcp.schemas.sprint import BudgetStatus

        resp = SprintResponse(
            status="created",
            sprint_id="s-1",
            summary="ok",
            budget_status=BudgetStatus(
                approved_usd=100.0, spent_usd=0.0, remaining_usd=100.0, alert=False
            ),
            next_action="next",
            idempotency_key="my-key",
        )
        assert resp.idempotency_key == "my-key"
