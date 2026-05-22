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


def _sprint_ctx(sprint: object = None, asset_count: int = 0, new_id: uuid.UUID | None = None) -> MagicMock:
    _new_id = new_id or uuid.uuid4()
    session = AsyncMock()
    session.get = AsyncMock(return_value=sprint)
    scalar_result = MagicMock()
    scalar_result.scalar_one = MagicMock(return_value=asset_count)
    session.execute = AsyncMock(return_value=scalar_result)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, "id", _new_id))

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


@pytest.mark.asyncio
async def test_create_creative_sprint_success() -> None:
    from vos_studio_mcp.services.sprint_service import create_creative_sprint

    fixed_id = uuid.uuid4()
    data = _make_sprint_input(client_id="00000000-0000-0000-0000-000000000001")
    ctx = _sprint_ctx(new_id=fixed_id)

    with (
        patch(_GUARD),
        patch(_GET_SESSION, return_value=ctx),
        patch(_SET_TENANT, new_callable=AsyncMock),
        patch(_GET_LIBRARY, new_callable=AsyncMock, return_value=[]),
    ):
        result = await create_creative_sprint(data)

    assert result.status == "created"
    assert result.sprint_id == str(fixed_id)
    assert result.budget_status.approved_usd == 500.0
    assert result.next_action == "prepare_dashboard_pack"
    assert result.variant_groups_created == 0


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
    ctx = _sprint_ctx()

    with (
        patch(_GUARD),
        patch(_GET_SESSION, return_value=ctx),
        patch(_SET_TENANT, new_callable=AsyncMock),
        patch(_GET_LIBRARY, new_callable=AsyncMock, return_value=[]),
    ):
        result = await create_creative_sprint(data)

    assert result.status == "created"
    assert result.variant_groups_created == 1


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
    ctx = _sprint_ctx(sprint=sprint)

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

    ctx = _sprint_ctx(sprint=None)

    with patch(_GET_SESSION, return_value=ctx), pytest.raises(VosError) as exc:
        await close_sprint(CloseSprintInput(sprint_id=str(uuid.uuid4())))

    assert exc.value.error_code == ErrorCode.NOT_FOUND


@pytest.mark.asyncio
async def test_close_sprint_already_closed() -> None:
    from vos_studio_mcp.errors import ErrorCode, VosError
    from vos_studio_mcp.schemas.sprint import CloseSprintInput
    from vos_studio_mcp.services.sprint_service import close_sprint

    sprint = _mock_sprint_orm(sprint_status="closed")
    ctx = _sprint_ctx(sprint=sprint)

    with patch(_GET_SESSION, return_value=ctx), pytest.raises(VosError) as exc:
        await close_sprint(CloseSprintInput(sprint_id=str(uuid.uuid4())))

    assert exc.value.error_code == ErrorCode.INVALID_INPUT
