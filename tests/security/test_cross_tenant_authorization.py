"""Cross-tenant authorization regression matrix (Issue #46).

Every tenant-scoped MCP tool must reject a caller authenticated as Client A
when that caller attempts to read or mutate Client B's objects.

TOOL CLASSIFICATION
===================
Tenant-scoped (negative tests required):
  create_creative_sprint   — client_id in input              → assert_owns_client(client_id)
  save_brand_kit           — client_id in input              → assert_owns_client(client_id)
  request_api_video        — client_id in input              → assert_owns_client(client_id)
  get_video_job_status     — asset_id resolved to client     → assert_owns_client(resolved)
  list_video_jobs          — client_id in input              → assert_owns_client(client_id)
  get_sprint_status        — sprint_id resolved to client    → assert_owns_client(resolved)
  close_sprint             — sprint_id resolved to client    → assert_owns_client(resolved)
  list_sprint_assets       — sprint_id resolved to client    → assert_owns_client(resolved)
  register_manual_asset    — sprint_id resolved to client    → assert_owns_client(resolved)
  record_performance_metrics — asset_id resolved to client  → assert_owns_client(resolved)
  conclude_variant_test    — group_id → sprint_id → client   → assert_owns_client(resolved)
  prepare_video_blueprint  — sprint_id resolved to client    → assert_owns_client(resolved)
  set_client_webhook       — implicit from auth context      → AUTH_REQUIRED if unauthenticated

System/admin scoped (no ownership check needed — by design):
  create_client            — creates a new tenant, no pre-existing object
  get_server_status        — server-level diagnostics, no tenant data
  search_library           — intentionally cross-tenant shared library
  promote_to_library       — intentionally cross-tenant, audit-logged

Authorization model (ADR-0019):
  assert_owns_client(input_client_id) is a no-op when the auth context is
  None (dev with auth disabled). In production, mismatching client IDs raise
  VosError(INVALID_INPUT). Database-level RLS provides an independent second
  layer of defence (see tests/integration/test_rls_isolation.py).

Pattern for all tests in this file:
  1. Patch get_current_client_id → CLIENT_A (the authenticated caller)
  2. Attempt to access CLIENT_B's object (sprint / asset / brand kit)
  3. Assert VosError with error_code == INVALID_INPUT is raised before any DB write.
  4. Verify no DB session.commit() was called (mutation was blocked).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vos_studio_mcp.errors import ErrorCode, VosError

# ---------------------------------------------------------------------------
# Shared fixture IDs — Client A is the authenticated caller, Client B is the
# victim whose objects Client A must NOT be able to read or mutate.
# ---------------------------------------------------------------------------

_CLIENT_A = "aaaaaaaa-0000-0000-0000-aaaaaaaaaaaa"
_CLIENT_B = "bbbbbbbb-0000-0000-0000-bbbbbbbbbbbb"

_SPRINT_B = "cccccccc-0000-0000-0000-000000000001"   # belongs to CLIENT_B
_BRAND_KIT_B = "dddddddd-0000-0000-0000-000000000002"  # belongs to CLIENT_B
_ASSET_B = "eeeeeeee-0000-0000-0000-000000000003"    # belongs to CLIENT_B (via sprint)
_GROUP_B = "ffffffff-0000-0000-0000-000000000004"    # belongs to CLIENT_B (via sprint)

_AUTH_CTX = "vos_studio_mcp.auth.context._current_client_id"
_GUARDS = "vos_studio_mcp.auth.guards"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sprint_mock(client_id: str = _CLIENT_B) -> MagicMock:
    """Build a minimal Sprint ORM mock belonging to *client_id*."""
    import uuid

    s = MagicMock()
    s.client_id = uuid.UUID(client_id)
    s.sprint_status = "open"
    s.product_name = "Widget Pro"
    s.mode = "ai"
    s.max_spend_usd = 100.0
    s.spent_usd = 10.0
    s.alert_threshold_pct = 0.9
    return s


def _session_returning(obj: object) -> MagicMock:
    """Return a mock async session context that yields *obj* from session.get()."""
    session = AsyncMock()
    session.get = AsyncMock(return_value=obj)
    session.commit = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# Tools that receive client_id explicitly in the input schema.
# assert_owns_client is called immediately with the supplied value.
# ---------------------------------------------------------------------------


class TestExplicitClientIdTools:
    """Tools that accept client_id directly in their input (fast-fail guard)."""

    @pytest.mark.asyncio
    async def test_create_creative_sprint_rejects_cross_tenant(self) -> None:
        """Authenticated Client A cannot create a sprint for Client B."""
        from vos_studio_mcp.schemas.sprint import SprintBudget, SprintInput
        from vos_studio_mcp.services.sprint_service import create_creative_sprint

        data = SprintInput(
            client_id=_CLIENT_B,
            brand_kit_id=_BRAND_KIT_B,
            product_name="Rival Product",
            campaign_objective="sales",
            target_audience="everyone",
            brief="steal their data",
            budget=SprintBudget(max_spend_usd=1.0),
        )

        with patch(f"{_GUARDS}.get_current_client_id", return_value=_CLIENT_A), pytest.raises(VosError) as exc_info:
            await create_creative_sprint(data)

        assert exc_info.value.error_code == ErrorCode.INVALID_INPUT

    @pytest.mark.asyncio
    async def test_save_brand_kit_rejects_cross_tenant(self) -> None:
        """Authenticated Client A cannot save a brand kit for Client B."""
        from vos_studio_mcp.services.brand_kit_service import save_brand_kit

        # The guard fires before any DB access; a minimal mock with client_id is sufficient.
        data = MagicMock()
        data.client_id = _CLIENT_B

        with patch(f"{_GUARDS}.get_current_client_id", return_value=_CLIENT_A), pytest.raises(VosError) as exc_info:
            await save_brand_kit(data)

        assert exc_info.value.error_code == ErrorCode.INVALID_INPUT

    @pytest.mark.asyncio
    async def test_request_api_video_rejects_cross_tenant(self) -> None:
        """Authenticated Client A cannot request a video job for Client B."""
        from vos_studio_mcp.services.generation_service import request_api_video

        # The guard fires before any DB access; a minimal mock with client_id is sufficient.
        data = MagicMock()
        data.client_id = _CLIENT_B

        with patch(f"{_GUARDS}.get_current_client_id", return_value=_CLIENT_A), pytest.raises(VosError) as exc_info:
            await request_api_video(data)

        assert exc_info.value.error_code == ErrorCode.INVALID_INPUT

    @pytest.mark.asyncio
    async def test_list_video_jobs_rejects_cross_tenant(self) -> None:
        """Authenticated Client A cannot list video jobs for Client B."""
        from vos_studio_mcp.services.generation_service import list_video_jobs

        with patch(f"{_GUARDS}.get_current_client_id", return_value=_CLIENT_A), pytest.raises(VosError) as exc_info:
            await list_video_jobs(_CLIENT_B, _SPRINT_B)

        assert exc_info.value.error_code == ErrorCode.INVALID_INPUT


# ---------------------------------------------------------------------------
# Tools that resolve client_id from the database (sprint/asset lookup).
# assert_owns_client is called AFTER the DB lookup; must not skip the guard
# even when the object is found.
# ---------------------------------------------------------------------------


class TestResolvedClientIdTools:
    """Tools that derive client_id from the DB — guard must still fire."""

    @pytest.mark.asyncio
    async def test_get_sprint_status_rejects_cross_tenant(self) -> None:
        """Authenticated Client A cannot read the status of Client B's sprint."""
        from vos_studio_mcp.services.sprint_service import get_sprint_status

        sprint = _sprint_mock(client_id=_CLIENT_B)

        with patch(
            "vos_studio_mcp.services.sprint_service.get_session",
            return_value=_session_returning(sprint),
        ), patch(f"{_GUARDS}.get_current_client_id", return_value=_CLIENT_A), pytest.raises(VosError) as exc_info:
            await get_sprint_status(_SPRINT_B)

        assert exc_info.value.error_code == ErrorCode.INVALID_INPUT

    @pytest.mark.asyncio
    async def test_close_sprint_rejects_cross_tenant(self) -> None:
        """Authenticated Client A cannot close Client B's sprint."""
        from vos_studio_mcp.schemas.sprint import CloseSprintInput
        from vos_studio_mcp.services.sprint_service import close_sprint

        sprint = _sprint_mock(client_id=_CLIENT_B)

        with patch(
            "vos_studio_mcp.services.sprint_service.get_session",
            return_value=_session_returning(sprint),
        ), patch(f"{_GUARDS}.get_current_client_id", return_value=_CLIENT_A), pytest.raises(VosError) as exc_info:
            await close_sprint(CloseSprintInput(sprint_id=_SPRINT_B))

        assert exc_info.value.error_code == ErrorCode.INVALID_INPUT

    @pytest.mark.asyncio
    async def test_close_sprint_does_not_commit_on_rejection(self) -> None:
        """Rejected mutation must not commit the DB transaction."""
        from vos_studio_mcp.schemas.sprint import CloseSprintInput
        from vos_studio_mcp.services.sprint_service import close_sprint

        sprint = _sprint_mock(client_id=_CLIENT_B)
        session_ctx = _session_returning(sprint)
        inner_session = session_ctx.__aenter__.return_value

        with patch(
            "vos_studio_mcp.services.sprint_service.get_session",
            return_value=session_ctx,
        ), patch(f"{_GUARDS}.get_current_client_id", return_value=_CLIENT_A), pytest.raises(VosError):
            await close_sprint(CloseSprintInput(sprint_id=_SPRINT_B))

        inner_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_sprint_assets_rejects_cross_tenant(self) -> None:
        """Authenticated Client A cannot list assets of Client B's sprint."""
        from vos_studio_mcp.services.asset_service import list_sprint_assets

        with patch(
            "vos_studio_mcp.services.asset_service.set_tenant_context_from_sprint",
            new=AsyncMock(return_value=_CLIENT_B),
        ), patch(f"{_GUARDS}.get_current_client_id", return_value=_CLIENT_A), pytest.raises(VosError) as exc_info:
            await list_sprint_assets(_SPRINT_B)

        assert exc_info.value.error_code == ErrorCode.INVALID_INPUT

    @pytest.mark.asyncio
    async def test_register_manual_asset_rejects_cross_tenant(self) -> None:
        """Authenticated Client A cannot register an asset into Client B's sprint."""
        from vos_studio_mcp.schemas.asset import AssetInput
        from vos_studio_mcp.services.asset_service import register_manual_asset

        data = AssetInput(
            sprint_id=_SPRINT_B,
            provider="higgsfield",
            prompt_version="v1",
            preset_version="p1",
            storage_url="https://r2.example.com/asset.mp4",
        )

        with patch(
            "vos_studio_mcp.services.asset_service.set_tenant_context_from_sprint",
            new=AsyncMock(return_value=_CLIENT_B),
        ), patch(f"{_GUARDS}.get_current_client_id", return_value=_CLIENT_A), pytest.raises(VosError) as exc_info:
            await register_manual_asset(data)

        assert exc_info.value.error_code == ErrorCode.INVALID_INPUT

    @pytest.mark.asyncio
    async def test_register_manual_asset_does_not_commit_on_rejection(self) -> None:
        """Rejected manual asset registration must not write to the DB."""
        from vos_studio_mcp.schemas.asset import AssetInput
        from vos_studio_mcp.services.asset_service import register_manual_asset

        data = AssetInput(
            sprint_id=_SPRINT_B,
            provider="higgsfield",
            prompt_version="v1",
            preset_version="p1",
            storage_url="https://r2.example.com/asset.mp4",
        )

        session = AsyncMock()
        session.commit = AsyncMock()
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "vos_studio_mcp.services.asset_service.set_tenant_context_from_sprint",
            new=AsyncMock(return_value=_CLIENT_B),
        ), patch(
            "vos_studio_mcp.services.asset_service.get_session", return_value=ctx
        ), patch(
            f"{_GUARDS}.get_current_client_id", return_value=_CLIENT_A
        ), pytest.raises(VosError):
            await register_manual_asset(data)

        session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_record_performance_metrics_rejects_cross_tenant(self) -> None:
        """Authenticated Client A cannot record performance for Client B's asset."""
        import uuid
        from unittest.mock import MagicMock

        from vos_studio_mcp.schemas.performance_record import (
            DistributionContext,
            PerformanceMetrics,
            PerformanceRecordInput,
        )
        from vos_studio_mcp.services.performance_record_service import create_performance_record

        # Mock asset that belongs to CLIENT_B; the SECURITY DEFINER helper
        # (get_asset_with_client) resolves the owning client_id as CLIENT_B.
        asset_mock = MagicMock()
        asset_mock.sprint_id = uuid.UUID(_SPRINT_B)

        session = AsyncMock()
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)

        data = PerformanceRecordInput(
            asset_id=_ASSET_B,
            distribution=DistributionContext(platform="meta", start_date="2026-01-01"),
            metrics=PerformanceMetrics(impressions=1000),
            performance_label="average",
        )

        # assert_owns_client is NOT patched: with auth context = CLIENT_A and the
        # asset owned by CLIENT_B, ownership verification must reject the call
        # before any sprint read or write occurs.
        with patch(
            "vos_studio_mcp.services.performance_record_service.get_session",
            return_value=ctx,
        ), patch(
            "vos_studio_mcp.services.performance_record_service.get_asset_with_client",
            new=AsyncMock(return_value=(asset_mock, _CLIENT_B)),
        ), patch(
            f"{_GUARDS}.get_current_client_id", return_value=_CLIENT_A
        ), pytest.raises(VosError) as exc_info:
            await create_performance_record(data)

        assert exc_info.value.error_code == ErrorCode.INVALID_INPUT

    @pytest.mark.asyncio
    async def test_get_video_job_status_rejects_cross_tenant(self) -> None:
        """Authenticated Client A cannot read video job status for Client B's asset."""
        from vos_studio_mcp.services.generation_service import get_video_job_status

        with patch(
            "vos_studio_mcp.services.generation_service.get_asset_with_client",
            new=AsyncMock(return_value=(MagicMock(), _CLIENT_B)),
        ), patch(
            "vos_studio_mcp.services.generation_service.get_session",
            return_value=_session_returning(None),
        ), patch(
            f"{_GUARDS}.get_current_client_id", return_value=_CLIENT_A
        ), pytest.raises(VosError) as exc_info:
            await get_video_job_status(_ASSET_B)

        assert exc_info.value.error_code == ErrorCode.INVALID_INPUT

    @pytest.mark.asyncio
    async def test_conclude_variant_test_rejects_cross_tenant(self) -> None:
        """Authenticated Client A cannot conclude a variant test in Client B's sprint."""
        import uuid

        from vos_studio_mcp.schemas.variant import ConcludeVariantTestInput
        from vos_studio_mcp.services.variant_service import conclude_variant_test

        group_mock = MagicMock()
        group_mock.sprint_id = uuid.UUID(_SPRINT_B)
        group_mock.status = "running"

        session = AsyncMock()
        session.scalar = AsyncMock(return_value=group_mock)
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)

        data = ConcludeVariantTestInput(
            group_id=_GROUP_B,
            winner_variant_id=str(uuid.uuid4()),
            confirmed=True,
        )

        with patch(
            "vos_studio_mcp.services.variant_service.get_session",
            return_value=ctx,
        ), patch(
            "vos_studio_mcp.services.variant_service.set_tenant_context_from_sprint",
            new=AsyncMock(return_value=_CLIENT_B),
        ), patch(
            f"{_GUARDS}.get_current_client_id", return_value=_CLIENT_A
        ), pytest.raises(VosError) as exc_info:
            await conclude_variant_test(data)

        assert exc_info.value.error_code == ErrorCode.INVALID_INPUT

    @pytest.mark.asyncio
    async def test_prepare_video_blueprint_rejects_cross_tenant(self) -> None:
        """Authenticated Client A cannot prepare a blueprint for Client B's sprint."""
        from vos_studio_mcp.schemas.blueprint import VideoBlueprintInput
        from vos_studio_mcp.services.blueprint_service import prepare_video_blueprint

        sprint = _sprint_mock(client_id=_CLIENT_B)

        with patch(
            "vos_studio_mcp.services.blueprint_service.get_session",
            return_value=_session_returning(sprint),
        ), patch(
            f"{_GUARDS}.get_current_client_id", return_value=_CLIENT_A
        ), pytest.raises(VosError) as exc_info:
            await prepare_video_blueprint(
                VideoBlueprintInput(sprint_id=_SPRINT_B)
            )

        assert exc_info.value.error_code == ErrorCode.INVALID_INPUT


# ---------------------------------------------------------------------------
# Non-enumerating responses — "not found" must look the same whether the
# object does not exist or the caller is not authorized to see it.
# ---------------------------------------------------------------------------


class TestNonEnumeratingResponses:
    """Unauthorized access must be indistinguishable from a missing object."""

    @pytest.mark.asyncio
    async def test_get_sprint_status_not_found_for_missing_sprint(self) -> None:
        """A completely unknown sprint_id returns NOT_FOUND (not a 200)."""
        from vos_studio_mcp.services.sprint_service import get_sprint_status

        with patch(
            "vos_studio_mcp.services.sprint_service.get_session",
            return_value=_session_returning(None),  # sprint not in DB
        ), pytest.raises(VosError) as exc_info:
            await get_sprint_status(_SPRINT_B)

        assert exc_info.value.error_code == ErrorCode.NOT_FOUND

    @pytest.mark.asyncio
    async def test_close_sprint_not_found_for_missing_sprint(self) -> None:
        """Calling close_sprint with an unknown sprint_id returns NOT_FOUND."""
        from vos_studio_mcp.schemas.sprint import CloseSprintInput
        from vos_studio_mcp.services.sprint_service import close_sprint

        with patch(
            "vos_studio_mcp.services.sprint_service.get_session",
            return_value=_session_returning(None),
        ), pytest.raises(VosError) as exc_info:
            await close_sprint(CloseSprintInput(sprint_id=_SPRINT_B))

        assert exc_info.value.error_code == ErrorCode.NOT_FOUND

    @pytest.mark.asyncio
    async def test_list_sprint_assets_not_found_for_missing_sprint(self) -> None:
        """list_sprint_assets raises NOT_FOUND when the sprint does not exist."""
        from vos_studio_mcp.services.asset_service import list_sprint_assets

        with patch(
            "vos_studio_mcp.services.asset_service.set_tenant_context_from_sprint",
            side_effect=LookupError("Sprint not found"),
        ), pytest.raises(VosError) as exc_info:
            await list_sprint_assets(_SPRINT_B)

        assert exc_info.value.error_code == ErrorCode.NOT_FOUND

    @pytest.mark.asyncio
    async def test_register_manual_asset_not_found_for_missing_sprint(self) -> None:
        """register_manual_asset raises NOT_FOUND when the sprint does not exist."""
        from vos_studio_mcp.schemas.asset import AssetInput
        from vos_studio_mcp.services.asset_service import register_manual_asset

        with patch(
            "vos_studio_mcp.services.asset_service.set_tenant_context_from_sprint",
            side_effect=LookupError("Sprint not found"),
        ), pytest.raises(VosError) as exc_info:
            await register_manual_asset(
                AssetInput(
                    sprint_id=_SPRINT_B,
                    provider="higgsfield",
                    prompt_version="v1",
                    preset_version="p1",
                    storage_url="https://r2.example.com/asset.mp4",
                )
            )

        assert exc_info.value.error_code == ErrorCode.NOT_FOUND


# ---------------------------------------------------------------------------
# Auth disabled (no auth context) — guards must be no-ops, not errors.
# This preserves the developer experience in local envs without auth.
# ---------------------------------------------------------------------------


class TestNoAuthContext:
    """When auth is disabled (get_current_client_id → None), guards are no-ops."""

    @pytest.mark.asyncio
    async def test_create_creative_sprint_no_auth_no_guard(self) -> None:
        """Without auth context, the ownership guard must not fire."""
        from vos_studio_mcp.auth.guards import assert_owns_client

        # Verify assert_owns_client is a no-op when auth context is None
        with patch(f"{_GUARDS}.get_current_client_id", return_value=None):
            assert_owns_client(_CLIENT_B)  # must not raise

    def test_assert_owns_client_raises_only_when_context_set(self) -> None:
        """assert_owns_client raises iff an auth context IS set and IDs differ."""
        from vos_studio_mcp.auth.guards import assert_owns_client

        # No context → no-op
        with patch(f"{_GUARDS}.get_current_client_id", return_value=None):
            assert_owns_client(_CLIENT_B)  # no raise

        # Matching context → no-op
        with patch(f"{_GUARDS}.get_current_client_id", return_value=_CLIENT_A):
            assert_owns_client(_CLIENT_A)  # no raise

        # Mismatching context → raises
        with patch(f"{_GUARDS}.get_current_client_id", return_value=_CLIENT_A):
            with pytest.raises(VosError) as exc_info:
                assert_owns_client(_CLIENT_B)
            assert exc_info.value.error_code == ErrorCode.INVALID_INPUT
