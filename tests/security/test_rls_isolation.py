"""RLS and tenant isolation tests for migrations 0009 and 0010.

Referenced from test_cross_tenant_authorization.py docstring as
tests/security/test_rls_isolation.py.

Migration 0009 — webhook_url on clients
  Adds `webhook_url` column to `clients`.  RLS on `clients` already isolates
  rows by tenant.  The additional isolation concern here is that the
  set_client_webhook tool must only operate on the authenticated caller's own
  record — never on another tenant's record via a caller-supplied client_id.

Migration 0010 — idempotency_key on sprints
  Adds `idempotency_key` to `sprints` with a unique constraint scoped to
  (client_id, idempotency_key).  The isolation concern is that Client A's
  idempotency key must never match or expose Client B's sprints.

These tests are unit/service-level (no live DB), following the same pattern
as test_cross_tenant_authorization.py, since PostgreSQL RLS enforcement
requires a live database with the `app.tenant_id` session variable set.
The DB-level enforcement is exercised in CI via Docker-backed integration
tests (out of scope for this unit test suite).

ADR references: ADR-0023 (multitenancy), ADR-0033 (cross-tenant regression).
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vos_studio_mcp.errors import ErrorCode, VosError

# ---------------------------------------------------------------------------
# Identities
# ---------------------------------------------------------------------------

_CLIENT_A = "aaaaaaaa-0000-0000-0000-aaaaaaaaaaaa"
_CLIENT_B = "bbbbbbbb-0000-0000-0000-bbbbbbbbbbbb"
_SPRINT_A = "cccccccc-0000-0000-0000-000000000001"
_SPRINT_B = "dddddddd-0000-0000-0000-000000000002"
_IDEM_KEY = "order-retry-001"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_client(client_id: str = _CLIENT_A) -> MagicMock:
    c = MagicMock()
    c.id = uuid.UUID(client_id)
    c.webhook_url = None
    return c


def _mock_sprint(client_id: str = _CLIENT_B, sprint_id: str = _SPRINT_B) -> MagicMock:
    s = MagicMock()
    s.id = uuid.UUID(sprint_id)
    s.client_id = uuid.UUID(client_id)
    s.idempotency_key = _IDEM_KEY
    s.brand_kit_id = uuid.UUID("eeeeeeee-0000-0000-0000-000000000003")
    s.sprint_status = "open"
    s.product_name = "Product B"
    s.campaign_objective = "Awareness"
    s.target_audience = "Gen Z"
    s.brief = "Bold look"
    s.mode = "dashboard_manual"
    s.max_spend_usd = 100.0
    s.spent_usd = 0.0
    s.alert_threshold_pct = 0.8
    s.max_images = None
    s.max_videos = None
    s.performance_memory = {}
    return s


def _make_session_ctx(
    get_return: object = None,
    scalars_first: object = None,
) -> MagicMock:
    session = AsyncMock()
    session.get = AsyncMock(return_value=get_return)
    scalar_result = MagicMock()
    scalar_result.scalars = MagicMock(
        return_value=MagicMock(first=MagicMock(return_value=scalars_first))
    )
    session.execute = AsyncMock(return_value=scalar_result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# ===========================================================================
# Migration 0009 — webhook_url ownership isolation
# ===========================================================================


class TestWebhookUrlOwnershipIsolation:
    """set_client_webhook must use the auth context client_id, never caller input.

    The tool layer extracts the client_id from get_current_client_id() and
    passes it to the service.  The service uses bypass_rls + session.get(Client, cid)
    where cid comes from the auth context — never from tool input.  Passing a
    different client_id would require bypassing the tool layer entirely, which
    is not possible via the MCP protocol.

    These tests verify the tool enforces auth context before delegating.
    """

    @pytest.mark.asyncio
    async def test_tool_uses_auth_context_client_id_not_input(self) -> None:
        """The set_client_webhook tool must derive client_id from the auth
        context, not from any field the caller supplies.
        """

        from vos_studio_mcp.tools.set_client_webhook import register_set_client_webhook_tools

        captured: dict = {}
        mock_mcp = MagicMock()

        def _tool(**kwargs):
            def decorator(fn):
                captured[fn.__name__] = fn
                return fn
            return decorator

        mock_mcp.tool = _tool
        register_set_client_webhook_tools(mock_mcp)

        from vos_studio_mcp.schemas.client import SetClientWebhookInput, SetClientWebhookResponse

        mock_resp = SetClientWebhookResponse(
            status="updated",
            client_id=_CLIENT_A,
            webhook_url="https://hooks.example.com/ok",
            summary="Webhook URL set.",
        )

        # Auth context says CLIENT_A; tool must forward CLIENT_A to service
        with (
            patch(
                "vos_studio_mcp.tools.set_client_webhook.get_current_client_id",
                return_value=_CLIENT_A,
            ),
            patch(
                "vos_studio_mcp.tools.set_client_webhook.set_webhook_service",
                new=AsyncMock(return_value=mock_resp),
            ) as mock_svc,
        ):
            result = await captured["set_client_webhook"](
                data=SetClientWebhookInput(webhook_url="https://hooks.example.com/ok")
            )

        # Service was called with CLIENT_A (from context), not any injected id
        call_args = mock_svc.call_args
        assert call_args.args[0] == _CLIENT_A
        assert result.client_id == _CLIENT_A

    @pytest.mark.asyncio
    async def test_tool_raises_auth_required_when_unauthenticated(self) -> None:
        """If the auth context has no client_id, the tool must reject the call."""
        from vos_studio_mcp.schemas.client import SetClientWebhookInput
        from vos_studio_mcp.tools.set_client_webhook import register_set_client_webhook_tools

        captured: dict = {}
        mock_mcp = MagicMock()

        def _tool(**kwargs):
            def decorator(fn):
                captured[fn.__name__] = fn
                return fn
            return decorator

        mock_mcp.tool = _tool
        register_set_client_webhook_tools(mock_mcp)

        with (
            patch(
                "vos_studio_mcp.tools.set_client_webhook.get_current_client_id",
                return_value=None,
            ),
            pytest.raises(VosError) as exc_info,
        ):
            await captured["set_client_webhook"](
                data=SetClientWebhookInput(webhook_url="https://hooks.example.com/ok")
            )

        assert exc_info.value.error_code == ErrorCode.AUTH_REQUIRED

    @pytest.mark.asyncio
    async def test_service_rejects_nonexistent_client(self) -> None:
        """set_client_webhook service must raise NOT_FOUND for an unknown client_id.

        Even if a caller somehow passes a fabricated client_id directly to the
        service, the service's session.get() returns None → NOT_FOUND raised
        before any write.
        """
        from vos_studio_mcp.schemas.client import SetClientWebhookInput
        from vos_studio_mcp.services.client_service import set_client_webhook

        ctx = _make_session_ctx(get_return=None)  # client not found

        with (
            patch(
                "vos_studio_mcp.services.client_service.get_session",
                return_value=ctx,
            ),
            patch(
                "vos_studio_mcp.services.client_service.bypass_rls",
                new_callable=AsyncMock,
            ),
            patch(
                "vos_studio_mcp.services.client_service.validate_webhook_url",
            ),
            pytest.raises(VosError) as exc_info,
        ):
            await set_client_webhook(
                _CLIENT_B,
                SetClientWebhookInput(webhook_url="https://hooks.example.com/ok"),
            )

        assert exc_info.value.error_code == ErrorCode.NOT_FOUND
        session_mock = ctx.__aenter__.return_value
        session_mock.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_service_does_not_commit_on_not_found(self) -> None:
        """When the client is not found, no DB write must occur."""
        from vos_studio_mcp.schemas.client import SetClientWebhookInput
        from vos_studio_mcp.services.client_service import set_client_webhook

        ctx = _make_session_ctx(get_return=None)
        session_mock = ctx.__aenter__.return_value

        with (
            patch("vos_studio_mcp.services.client_service.get_session", return_value=ctx),
            patch("vos_studio_mcp.services.client_service.bypass_rls", new_callable=AsyncMock),
            patch("vos_studio_mcp.services.client_service.validate_webhook_url"),
            pytest.raises(VosError),
        ):
            await set_client_webhook(
                _CLIENT_B,
                SetClientWebhookInput(webhook_url="https://hooks.example.com/ok"),
            )

        session_mock.add.assert_not_called()
        session_mock.commit.assert_not_awaited()


# ===========================================================================
# Migration 0010 — idempotency_key tenant scoping
# ===========================================================================


class TestIdempotencyKeyTenantScoping:
    """The idempotency key lookup must be scoped to the authenticated client.

    _find_idempotent_sprint() queries WHERE client_id = <auth_client> AND
    idempotency_key = <key>.  This means:
    - Client A using key "X" can only find Client A's sprint with key "X".
    - Client B using key "X" finds no sprint (because the query also filters
      by client_b's client_id, and Client A's sprint has client_a's client_id).

    The unique DB constraint enforces (client_id, idempotency_key) uniqueness,
    so two clients can legitimately use the same key for their own sprints.
    """

    @pytest.mark.asyncio
    async def test_idempotency_lookup_scoped_to_caller_client(self) -> None:
        """When Client B uses a key that Client A already used, a NEW sprint is
        created — the lookup must not return Client A's sprint.
        """
        from vos_studio_mcp.schemas.sprint import SprintBudget, SprintInput
        from vos_studio_mcp.services.sprint_service import create_creative_sprint

        # The session returns None for scalars().first() — simulating that no
        # sprint with (CLIENT_B, _IDEM_KEY) exists even though CLIENT_A has one.
        ctx = _make_session_ctx(scalars_first=None)
        session_mock = ctx.__aenter__.return_value

        # Mock the brand_kit refresh call
        brand_kit_mock = MagicMock()
        brand_kit_mock.performance_memory = {}
        session_mock.get = AsyncMock(return_value=brand_kit_mock)
        session_mock.refresh = AsyncMock(
            side_effect=lambda obj: setattr(
                obj, "id", uuid.UUID("ffffffff-0000-0000-0000-000000000001")
            )
        )

        data = SprintInput(
            client_id=_CLIENT_B,
            brand_kit_id=str(uuid.uuid4()),
            product_name="Product B",
            campaign_objective="Awareness",
            target_audience="Gen Z",
            brief="Bold look",
            budget=SprintBudget(max_spend_usd=100.0),
            idempotency_key=_IDEM_KEY,
        )

        with (
            patch(
                "vos_studio_mcp.services.sprint_service.assert_owns_client"
            ),
            patch(
                "vos_studio_mcp.services.sprint_service.check_rate_limit",
                new_callable=AsyncMock,
            ),
            patch(
                "vos_studio_mcp.services.sprint_service.get_session",
                return_value=ctx,
            ),
            patch(
                "vos_studio_mcp.services.sprint_service.set_tenant_context",
                new_callable=AsyncMock,
            ),
            patch(
                "vos_studio_mcp.services.sprint_service.get_top_performers",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "vos_studio_mcp.services.sprint_service.get_library_suggestions",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "vos_studio_mcp.services.sprint_service.emit_audit_event",
                new_callable=AsyncMock,
            ),
        ):
            result = await create_creative_sprint(data)

        # A new sprint was created (not a replay), so audit is emitted and
        # session.commit() was called
        session_mock.add.assert_called()
        session_mock.commit.assert_awaited()
        assert result.status == "created"

    @pytest.mark.asyncio
    async def test_idempotency_key_replay_returns_same_sprint_for_same_client(self) -> None:
        """When Client A re-uses a key that matches an existing CLIENT_A sprint,
        the existing sprint is returned — no new sprint created.
        """
        from vos_studio_mcp.schemas.sprint import SprintBudget, SprintInput
        from vos_studio_mcp.services.sprint_service import create_creative_sprint

        existing_sprint = _mock_sprint(client_id=_CLIENT_A, sprint_id=_SPRINT_A)

        # Session returns the existing sprint for the idempotency lookup
        ctx = _make_session_ctx(scalars_first=existing_sprint)
        session_mock = ctx.__aenter__.return_value
        session_mock.get = AsyncMock(return_value=MagicMock(performance_memory={}))

        data = SprintInput(
            client_id=_CLIENT_A,
            brand_kit_id=str(uuid.uuid4()),
            product_name="Product A",
            campaign_objective="Awareness",
            target_audience="Gen Z",
            brief="Bold look",
            budget=SprintBudget(max_spend_usd=100.0),
            idempotency_key=_IDEM_KEY,
        )

        with (
            patch("vos_studio_mcp.services.sprint_service.assert_owns_client"),
            patch(
                "vos_studio_mcp.services.sprint_service.check_rate_limit",
                new_callable=AsyncMock,
            ),
            patch("vos_studio_mcp.services.sprint_service.get_session", return_value=ctx),
            patch(
                "vos_studio_mcp.services.sprint_service.set_tenant_context",
                new_callable=AsyncMock,
            ),
            patch(
                "vos_studio_mcp.services.sprint_service.get_top_performers",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "vos_studio_mcp.services.sprint_service.get_library_suggestions",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await create_creative_sprint(data)

        # Replay — no new sprint inserted
        session_mock.add.assert_not_called()
        assert result.status == "created"
        assert result.sprint_id == _SPRINT_A

    @pytest.mark.asyncio
    async def test_idempotency_query_includes_client_id_filter(self) -> None:
        """_find_idempotent_sprint must include the caller's client_id in its
        WHERE clause so cross-tenant key collisions are impossible.
        """
        from vos_studio_mcp.services.sprint_service import _find_idempotent_sprint

        # Capture the executed query
        session = AsyncMock()
        scalar_result = MagicMock()
        scalar_result.scalars = MagicMock(
            return_value=MagicMock(first=MagicMock(return_value=None))
        )
        session.execute = AsyncMock(return_value=scalar_result)

        result = await _find_idempotent_sprint(session, _CLIENT_A, _IDEM_KEY)

        # The query was executed once
        session.execute.assert_awaited_once()

        # Verify the query contains a WHERE clause (the compiled SQL should
        # reference both client_id and idempotency_key).
        call = session.execute.call_args
        query = call.args[0]
        compiled = str(query.compile(compile_kwargs={"literal_binds": True}))
        # UUID may be rendered without dashes in dialect-specific compilation.
        client_id_no_dashes = _CLIENT_A.replace("-", "")
        assert client_id_no_dashes in compiled or _CLIENT_A in compiled
        assert _IDEM_KEY in compiled
        assert result is None
