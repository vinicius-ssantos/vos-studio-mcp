"""Unit tests for sprint_service — schemas and service functions."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

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


# ---------------------------------------------------------------------------
# Service function tests — mocked AsyncSession
# ---------------------------------------------------------------------------

_GUARD = "vos_studio_mcp.services.sprint_service.assert_owns_client"
_GET_SESSION = "vos_studio_mcp.services.sprint_service.get_session"
_SET_TENANT = "vos_studio_mcp.services.sprint_service.set_tenant_context"
_GET_LIBRARY = "vos_studio_mcp.services.sprint_service.get_library_suggestions"
_GET_TOP_PERFORMERS = "vos_studio_mcp.services.sprint_service.get_top_performers"


def _mock_sprint_orm(**kwargs: object) -> MagicMock:
    s = MagicMock()
    s.id = uuid.uuid4()
    s.product_name = kwargs.get("product_name", "Summer Campaign")
    s.mode = kwargs.get("mode", "dashboard_manual")
    s.sprint_status = kwargs.get("sprint_status", "open")
    s.max_spend_usd = kwargs.get("max_spend_usd", 500.0)
    s.spent_usd = kwargs.get("spent_usd", 0.0)
    s.alert_threshold_pct = kwargs.get("alert_threshold_pct", 0.8)
    return s


def _brand_kit_ctx(brand_kit: object = None) -> MagicMock:
    """Return a minimal async context manager mock for the brand_kit lookup session."""
    session = AsyncMock()
    session.get = AsyncMock(return_value=brand_kit)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _sprint_ctx(
    sprint: object = None,
    asset_count: int = 0,
    new_id: uuid.UUID | None = None,
    has_final_approved: bool = True,
) -> MagicMock:
    _new_id = new_id or uuid.uuid4()
    session = AsyncMock()
    session.get = AsyncMock(return_value=sprint)

    # execute() is used for both asset_count (scalar_one) and final-asset guard (scalars().first())
    scalar_count_result = MagicMock()
    scalar_count_result.scalar_one = MagicMock(return_value=asset_count)

    final_asset_result = MagicMock()
    approved_asset = MagicMock() if has_final_approved else None
    final_asset_result.scalars.return_value.first.return_value = approved_asset

    # Return different mock on each call: first call → scalar count, second → final asset check
    session.execute = AsyncMock(side_effect=[scalar_count_result, final_asset_result])
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, "id", _new_id))

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _close_sprint_ctx(
    sprint: object = None,
    has_final_approved: bool = True,
) -> MagicMock:
    """Minimal context for close_sprint — only needs get + execute."""
    session = AsyncMock()
    session.get = AsyncMock(return_value=sprint)

    final_asset_result = MagicMock()
    approved_asset = MagicMock() if has_final_approved else None
    final_asset_result.scalars.return_value.first.return_value = approved_asset
    session.execute = AsyncMock(return_value=final_asset_result)
    session.commit = AsyncMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


@pytest.mark.asyncio
async def test_create_creative_sprint_success() -> None:
    from vos_studio_mcp.services.sprint_service import create_creative_sprint

    fixed_id = uuid.uuid4()
    data = _make_sprint_input(client_id="00000000-0000-0000-0000-000000000001")
    sprint_ctx = _sprint_ctx(new_id=fixed_id)
    bk_ctx = _brand_kit_ctx(brand_kit=None)  # no brand_kit → performance_context is None

    with (
        patch(_GUARD),
        patch(_GET_SESSION, side_effect=[sprint_ctx, bk_ctx]),
        patch(_SET_TENANT, new_callable=AsyncMock),
        patch(_GET_LIBRARY, new_callable=AsyncMock, return_value=[]),
        patch(_GET_TOP_PERFORMERS, new_callable=AsyncMock, return_value=[]),
    ):
        result = await create_creative_sprint(data)

    assert result.status == "created"
    assert result.sprint_id == str(fixed_id)
    assert result.budget_status.approved_usd == 500.0
    assert result.next_action == "prepare_dashboard_pack"
    assert result.variant_groups_created == 0
    assert result.performance_context is None


@pytest.mark.asyncio
async def test_create_creative_sprint_with_variant_groups() -> None:
    from vos_studio_mcp.schemas.sprint import VariantGroupInput, VariantInput
    from vos_studio_mcp.services.sprint_service import create_creative_sprint

    data = _make_sprint_input(
        client_id="00000000-0000-0000-0000-000000000001",
        variant_groups=[
            VariantGroupInput(
                hypothesis="Bold vs subtle",
                variable="tone",
                variants=[
                    VariantInput(label="A", description="Bold", prompt_version="v1", preset_version="p1"),
                    VariantInput(label="B", description="Subtle", prompt_version="v1", preset_version="p1"),
                ],
            )
        ],
    )
    sprint_ctx = _sprint_ctx()
    bk_ctx = _brand_kit_ctx(brand_kit=None)

    with (
        patch(_GUARD),
        patch(_GET_SESSION, side_effect=[sprint_ctx, bk_ctx]),
        patch(_SET_TENANT, new_callable=AsyncMock),
        patch(_GET_LIBRARY, new_callable=AsyncMock, return_value=[]),
        patch(_GET_TOP_PERFORMERS, new_callable=AsyncMock, return_value=[]),
    ):
        result = await create_creative_sprint(data)

    assert result.status == "created"
    assert result.variant_groups_created == 1


@pytest.mark.asyncio
async def test_create_creative_sprint_with_performance_context() -> None:
    """When brand_kit has performance memory, performance_context is populated."""
    from vos_studio_mcp.schemas.performance_record import TopPerformer
    from vos_studio_mcp.services.sprint_service import create_creative_sprint

    data = _make_sprint_input(client_id="00000000-0000-0000-0000-000000000001")
    sprint_ctx = _sprint_ctx()

    brand_kit_mock = MagicMock()
    brand_kit_mock.performance_memory = {
        "proven_angles": ["summer vibes", "bold CTA"],
        "proven_hooks": ["question hook"],
        "failed_approaches": ["low contrast"],
    }
    bk_ctx = _brand_kit_ctx(brand_kit=brand_kit_mock)

    fake_performer = TopPerformer(
        asset_id=str(uuid.uuid4()),
        platform="meta",
        performance_label="top_performer",
        ctr=0.04,
        roas=3.5,
        impressions=80_000,
        recorded_at="2026-05-01T00:00:00",
    )

    with (
        patch(_GUARD),
        patch(_GET_SESSION, side_effect=[sprint_ctx, bk_ctx]),
        patch(_SET_TENANT, new_callable=AsyncMock),
        patch(_GET_LIBRARY, new_callable=AsyncMock, return_value=[]),
        patch(_GET_TOP_PERFORMERS, new_callable=AsyncMock, return_value=[fake_performer]),
    ):
        result = await create_creative_sprint(data)

    assert result.performance_context is not None
    assert "summer vibes" in result.performance_context.top_angles
    assert "bold CTA" in result.performance_context.top_angles
    assert "question hook" in result.performance_context.proven_hooks
    assert "low contrast" in result.performance_context.avoid_approaches
    assert len(result.performance_context.top_performers) == 1
    assert result.performance_context.top_performers[0].platform == "meta"


@pytest.mark.asyncio
async def test_get_sprint_status_success() -> None:
    from vos_studio_mcp.services.sprint_service import get_sprint_status

    sprint = _mock_sprint_orm(sprint_status="open", max_spend_usd=100.0, spent_usd=20.0)
    ctx = _sprint_ctx(sprint=sprint, asset_count=3)

    with patch(_GET_SESSION, return_value=ctx):
        result = await get_sprint_status(str(uuid.uuid4()))

    assert result.status == "ok"
    assert result.sprint_status == "open"
    assert result.asset_count == 3
    assert result.budget_status.spent_usd == 20.0
    assert result.next_action == "prepare_dashboard_pack"


@pytest.mark.asyncio
async def test_get_sprint_status_not_found() -> None:
    from vos_studio_mcp.errors import ErrorCode, VosError
    from vos_studio_mcp.services.sprint_service import get_sprint_status

    ctx = _sprint_ctx(sprint=None)

    with patch(_GET_SESSION, return_value=ctx), pytest.raises(VosError) as exc:
        await get_sprint_status(str(uuid.uuid4()))

    assert exc.value.error_code == ErrorCode.NOT_FOUND


@pytest.mark.asyncio
async def test_get_sprint_status_budget_alert() -> None:
    from vos_studio_mcp.services.sprint_service import get_sprint_status

    sprint = _mock_sprint_orm(max_spend_usd=100.0, spent_usd=85.0, alert_threshold_pct=0.8)
    ctx = _sprint_ctx(sprint=sprint)

    with patch(_GET_SESSION, return_value=ctx):
        result = await get_sprint_status(str(uuid.uuid4()))

    assert result.budget_status.alert is True
    assert result.next_action == "review_budget_before_continuing"


@pytest.mark.asyncio
async def test_get_sprint_status_closed_sprint_next_action() -> None:
    from vos_studio_mcp.services.sprint_service import get_sprint_status

    sprint = _mock_sprint_orm(sprint_status="closed", spent_usd=0.0, max_spend_usd=100.0, alert_threshold_pct=0.8)
    ctx = _sprint_ctx(sprint=sprint)

    with patch(_GET_SESSION, return_value=ctx):
        result = await get_sprint_status(str(uuid.uuid4()))

    assert result.next_action == "no_action_sprint_closed"


@pytest.mark.asyncio
async def test_close_sprint_success() -> None:
    from vos_studio_mcp.schemas.sprint import CloseSprintInput
    from vos_studio_mcp.services.sprint_service import close_sprint

    sprint = _mock_sprint_orm(sprint_status="open")
    ctx = _close_sprint_ctx(sprint=sprint, has_final_approved=True)

    with patch(_GET_SESSION, return_value=ctx):
        result = await close_sprint(CloseSprintInput(sprint_id=str(uuid.uuid4())))

    assert result.status == "closed"
    assert result.sprint_status == "closed"
    assert result.next_action == "record_asset_performance"


@pytest.mark.asyncio
async def test_close_sprint_not_found() -> None:
    from vos_studio_mcp.errors import ErrorCode, VosError
    from vos_studio_mcp.schemas.sprint import CloseSprintInput
    from vos_studio_mcp.services.sprint_service import close_sprint

    ctx = _close_sprint_ctx(sprint=None)

    with patch(_GET_SESSION, return_value=ctx), pytest.raises(VosError) as exc:
        await close_sprint(CloseSprintInput(sprint_id=str(uuid.uuid4())))

    assert exc.value.error_code == ErrorCode.NOT_FOUND


@pytest.mark.asyncio
async def test_close_sprint_already_closed() -> None:
    from vos_studio_mcp.errors import ErrorCode, VosError
    from vos_studio_mcp.schemas.sprint import CloseSprintInput
    from vos_studio_mcp.services.sprint_service import close_sprint

    sprint = _mock_sprint_orm(sprint_status="closed")
    ctx = _close_sprint_ctx(sprint=sprint)

    with patch(_GET_SESSION, return_value=ctx), pytest.raises(VosError) as exc:
        await close_sprint(CloseSprintInput(sprint_id=str(uuid.uuid4())))

    assert exc.value.error_code == ErrorCode.INVALID_INPUT


@pytest.mark.asyncio
async def test_close_sprint_requires_final_approved_asset() -> None:
    """close_sprint should raise VALIDATION_ERROR when no approved final-delivery asset exists."""
    from vos_studio_mcp.errors import ErrorCode, VosError
    from vos_studio_mcp.schemas.sprint import CloseSprintInput
    from vos_studio_mcp.services.sprint_service import close_sprint

    sprint = _mock_sprint_orm(sprint_status="open")
    ctx = _close_sprint_ctx(sprint=sprint, has_final_approved=False)

    with patch(_GET_SESSION, return_value=ctx), pytest.raises(VosError) as exc:
        await close_sprint(CloseSprintInput(sprint_id=str(uuid.uuid4())))

    assert exc.value.error_code == ErrorCode.VALIDATION_ERROR
    assert "final delivery" in exc.value.message.lower()


@pytest.mark.asyncio
async def test_close_sprint_force_bypasses_validation() -> None:
    """close_sprint with force=True should succeed even without an approved delivery asset."""
    from vos_studio_mcp.schemas.sprint import CloseSprintInput
    from vos_studio_mcp.services.sprint_service import close_sprint

    sprint = _mock_sprint_orm(sprint_status="open")
    # no approved asset but force=True
    session = AsyncMock()
    session.get = AsyncMock(return_value=sprint)
    session.commit = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch(_GET_SESSION, return_value=ctx):
        result = await close_sprint(CloseSprintInput(sprint_id=str(uuid.uuid4()), force=True))

    assert result.status == "closed"
    # execute should NOT have been called (no validation query)
    session.execute.assert_not_called()


# ---------------------------------------------------------------------------
# get_sprint_performance_summary tests
# ---------------------------------------------------------------------------


def _make_asset_mock(
    asset_stage: str | None = None,
    qa_status: str | None = None,
    performance_score: int | None = None,
) -> MagicMock:
    a = MagicMock()
    a.asset_stage = asset_stage
    a.qa_status = qa_status
    a.performance_score = performance_score
    return a


@pytest.mark.asyncio
async def test_get_sprint_performance_summary_groups_by_stage() -> None:
    from vos_studio_mcp.services.sprint_service import get_sprint_performance_summary

    sprint = _mock_sprint_orm()
    assets = [
        _make_asset_mock("stage_c", "approved", 4),
        _make_asset_mock("stage_c", "needs_repair", None),
        _make_asset_mock("final", "approved", 5),
    ]

    session = AsyncMock()
    session.get = AsyncMock(return_value=sprint)
    scalars_result = MagicMock()
    scalars_result.scalars.return_value.all.return_value = assets
    session.execute = AsyncMock(return_value=scalars_result)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch(_GET_SESSION, return_value=ctx):
        result = await get_sprint_performance_summary(str(uuid.uuid4()))

    assert result.status == "ok"
    assert result.total_assets == 3
    assert len(result.by_stage) == 2
    stage_map = {s.asset_stage: s for s in result.by_stage}
    assert stage_map["stage_c"].approved_count == 1
    assert stage_map["stage_c"].needs_repair_count == 1
    assert stage_map["stage_c"].avg_performance_score == 4.0
    assert stage_map["final"].approved_count == 1
    assert stage_map["final"].avg_performance_score == 5.0


@pytest.mark.asyncio
async def test_get_sprint_performance_summary_not_found() -> None:
    from vos_studio_mcp.errors import ErrorCode, VosError
    from vos_studio_mcp.services.sprint_service import get_sprint_performance_summary

    session = AsyncMock()
    session.get = AsyncMock(return_value=None)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch(_GET_SESSION, return_value=ctx), pytest.raises(VosError) as exc:
        await get_sprint_performance_summary(str(uuid.uuid4()))

    assert exc.value.error_code == ErrorCode.NOT_FOUND



# ---------------------------------------------------------------------------
# list_sprints tests
# ---------------------------------------------------------------------------


def _make_sprint_orm_with_date(**kwargs: object) -> MagicMock:
    import datetime as dt
    s = _mock_sprint_orm(**kwargs)
    s.created_at = dt.datetime(2026, 5, 1, tzinfo=dt.UTC)
    return s


@pytest.mark.asyncio
async def test_list_sprints_returns_items() -> None:
    from vos_studio_mcp.services.sprint_service import list_sprints

    cid = "00000000-0000-0000-0000-000000000001"
    sprint = _make_sprint_orm_with_date(product_name="Product A")
    sprint.id = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")

    session = AsyncMock()
    session.get = AsyncMock()

    # First execute → sprints list
    sprints_result = MagicMock()
    sprints_result.scalars.return_value.all.return_value = [sprint]

    # Second execute → asset counts
    count_result = MagicMock()
    count_result.all.return_value = [(sprint.id, 3)]

    session.execute = AsyncMock(side_effect=[sprints_result, count_result])

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(_GUARD),
        patch(_GET_SESSION, return_value=ctx),
        patch(_SET_TENANT, new_callable=AsyncMock),
    ):
        result = await list_sprints(cid)

    assert result.status == "ok"
    assert result.total == 1
    assert result.sprints[0].product_name == "Product A"
    assert result.sprints[0].asset_count == 3
    assert result.next_action == "get_sprint_status"


@pytest.mark.asyncio
async def test_list_sprints_empty_returns_create_action() -> None:
    from vos_studio_mcp.services.sprint_service import list_sprints

    cid = "00000000-0000-0000-0000-000000000001"

    session = AsyncMock()
    sprints_result = MagicMock()
    sprints_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=sprints_result)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(_GUARD),
        patch(_GET_SESSION, return_value=ctx),
        patch(_SET_TENANT, new_callable=AsyncMock),
    ):
        result = await list_sprints(cid)

    assert result.total == 0
    assert result.next_action == "create_creative_sprint"


@pytest.mark.asyncio
async def test_list_sprints_status_filter_passed() -> None:
    """When filters.status='open' is passed the result only contains open sprints."""
    from vos_studio_mcp.schemas.sprint import SprintListFilters
    from vos_studio_mcp.services.sprint_service import list_sprints

    cid = "00000000-0000-0000-0000-000000000001"
    open_sprint = _make_sprint_orm_with_date(sprint_status="open")
    open_sprint.id = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")

    session = AsyncMock()
    sprints_result = MagicMock()
    sprints_result.scalars.return_value.all.return_value = [open_sprint]
    count_result = MagicMock()
    count_result.all.return_value = [(open_sprint.id, 0)]
    session.execute = AsyncMock(side_effect=[sprints_result, count_result])

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(_GUARD),
        patch(_GET_SESSION, return_value=ctx),
        patch(_SET_TENANT, new_callable=AsyncMock),
    ):
        result = await list_sprints(cid, SprintListFilters(status="open"))

    assert all(s.sprint_status == "open" for s in result.sprints)
