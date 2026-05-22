"""Unit tests for variant_service.conclude_variant_test (ADR-0027)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.schemas.variant import ConcludeVariantTestInput

_SERVICE = "vos_studio_mcp.services.variant_service"
_GET_SESSION = f"{_SERVICE}.get_session"
_SET_TENANT = f"{_SERVICE}.set_tenant_context_from_sprint"


def _make_variant(label: str = "urgency") -> MagicMock:
    v = MagicMock()
    v.id = uuid.uuid4()
    v.label = label
    v.prompt_version = "v1"
    v.preset_version = "p1"
    return v


def _make_group(status: str = "running") -> MagicMock:
    group = MagicMock()
    group.id = uuid.uuid4()
    group.sprint_id = uuid.uuid4()
    group.hypothesis = "urgency hook outperforms social proof"
    group.variable = "hook_type"
    group.status = status
    group.winner_variant_id = None
    group.concluded_at = None
    v1 = _make_variant("urgency")
    v2 = _make_variant("social_proof")
    group.variants = [v1, v2]
    return group


@pytest.fixture
def mock_session_ctx(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    session = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(_GET_SESSION, lambda: cm)
    monkeypatch.setattr(_SET_TENANT, AsyncMock(return_value="client-123"))
    return session


# ---------------------------------------------------------------------------
# Preview mode (confirmed=False)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preview_does_not_commit(mock_session_ctx: MagicMock) -> None:
    from vos_studio_mcp.services.variant_service import conclude_variant_test

    group = _make_group()
    winner = group.variants[0]
    mock_session_ctx.scalar = AsyncMock(return_value=group)

    data = ConcludeVariantTestInput(
        group_id=str(group.id),
        winner_variant_id=str(winner.id),
        confirmed=False,
    )
    result = await conclude_variant_test(data)

    assert result.status == "preview"
    assert result.outcome == "concluded"
    mock_session_ctx.commit.assert_not_called()


@pytest.mark.asyncio
async def test_preview_inconclusive(mock_session_ctx: MagicMock) -> None:
    from vos_studio_mcp.services.variant_service import conclude_variant_test

    group = _make_group()
    mock_session_ctx.scalar = AsyncMock(return_value=group)

    data = ConcludeVariantTestInput(
        group_id=str(group.id),
        winner_variant_id=None,
        confirmed=False,
    )
    result = await conclude_variant_test(data)

    assert result.status == "preview"
    assert result.outcome == "inconclusive"
    assert result.winner_variant_id is None


# ---------------------------------------------------------------------------
# Commit mode (confirmed=True)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conclude_with_winner_commits(mock_session_ctx: MagicMock) -> None:
    from vos_studio_mcp.services.variant_service import conclude_variant_test

    group = _make_group()
    winner = group.variants[0]
    mock_session_ctx.scalar = AsyncMock(return_value=group)
    mock_session_ctx.refresh = AsyncMock()

    data = ConcludeVariantTestInput(
        group_id=str(group.id),
        winner_variant_id=str(winner.id),
        confirmed=True,
    )
    result = await conclude_variant_test(data)

    assert result.status == "ok"
    assert result.outcome == "concluded"
    assert result.winner_variant_id == str(winner.id)
    assert result.next_action == "save_brand_kit"
    mock_session_ctx.commit.assert_called_once()


@pytest.mark.asyncio
async def test_conclude_inconclusive_commits(mock_session_ctx: MagicMock) -> None:
    from vos_studio_mcp.services.variant_service import conclude_variant_test

    group = _make_group()
    mock_session_ctx.scalar = AsyncMock(return_value=group)
    mock_session_ctx.refresh = AsyncMock()

    data = ConcludeVariantTestInput(
        group_id=str(group.id),
        winner_variant_id=None,
        confirmed=True,
    )
    result = await conclude_variant_test(data)

    assert result.status == "ok"
    assert result.outcome == "inconclusive"
    assert result.winner_variant_id is None
    assert result.next_action == "list_sprint_assets"
    mock_session_ctx.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_group_not_found_raises(mock_session_ctx: MagicMock) -> None:
    from vos_studio_mcp.services.variant_service import conclude_variant_test

    mock_session_ctx.scalar = AsyncMock(return_value=None)

    data = ConcludeVariantTestInput(group_id=str(uuid.uuid4()), confirmed=True)
    with pytest.raises(VosError) as exc_info:
        await conclude_variant_test(data)
    assert exc_info.value.error_code == ErrorCode.NOT_FOUND


@pytest.mark.asyncio
async def test_already_concluded_raises(mock_session_ctx: MagicMock) -> None:
    from vos_studio_mcp.services.variant_service import conclude_variant_test

    group = _make_group(status="concluded")
    mock_session_ctx.scalar = AsyncMock(return_value=group)

    data = ConcludeVariantTestInput(group_id=str(group.id), confirmed=True)
    with pytest.raises(VosError) as exc_info:
        await conclude_variant_test(data)
    assert exc_info.value.error_code == ErrorCode.INVALID_INPUT


@pytest.mark.asyncio
async def test_winner_not_in_group_raises(mock_session_ctx: MagicMock) -> None:
    from vos_studio_mcp.services.variant_service import conclude_variant_test

    group = _make_group()
    mock_session_ctx.scalar = AsyncMock(return_value=group)

    data = ConcludeVariantTestInput(
        group_id=str(group.id),
        winner_variant_id=str(uuid.uuid4()),  # foreign UUID
        confirmed=True,
    )
    with pytest.raises(VosError) as exc_info:
        await conclude_variant_test(data)
    assert exc_info.value.error_code == ErrorCode.INVALID_INPUT


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_response_includes_all_variants(mock_session_ctx: MagicMock) -> None:
    from vos_studio_mcp.services.variant_service import conclude_variant_test

    group = _make_group()
    mock_session_ctx.scalar = AsyncMock(return_value=group)

    data = ConcludeVariantTestInput(
        group_id=str(group.id),
        winner_variant_id=None,
        confirmed=False,
    )
    result = await conclude_variant_test(data)
    assert len(result.variants) == 2
    labels = {v.label for v in result.variants}
    assert "urgency" in labels
    assert "social_proof" in labels
