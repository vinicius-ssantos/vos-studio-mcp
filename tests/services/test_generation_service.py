"""Unit tests for generation service — request_api_video (Issue #6 item A)."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.schemas.api_video import ApiVideoInput
from vos_studio_mcp.services.generation_service import request_api_video
from vos_studio_mcp.services.providers.base import CostEstimate, GenerationResult

_GUARD = "vos_studio_mcp.services.generation_service.assert_owns_client"
_GET_SESSION = "vos_studio_mcp.services.generation_service.get_session"
_GET_ADAPTER = "vos_studio_mcp.services.generation_service.get_adapter"
_SET_TENANT = "vos_studio_mcp.services.generation_service.set_tenant_context"


def _input(**kwargs: Any) -> ApiVideoInput:
    defaults: dict[str, Any] = {
        "sprint_id": "00000000-0000-0000-0000-000000000010",
        "client_id": "00000000-0000-0000-0000-000000000001",
        "prompt": "A cinematic product launch",
        "prompt_version": "v1",
        "preset_version": "p1",
        "approval_token": "approved-by-operator",
        "resolution": "720p",
        "duration_seconds": 5,
        "aspect_ratio": "16:9",
    }
    defaults.update(kwargs)
    return ApiVideoInput(**defaults)


def _mock_sprint(
    client_id: str = "00000000-0000-0000-0000-000000000001",
    status: str = "open",
    max_spend_usd: float = 10.0,
    spent_usd: float = 0.0,
    max_videos: int | None = None,
) -> MagicMock:
    sprint = MagicMock()
    sprint.id = "00000000-0000-0000-0000-000000000010"
    sprint.client_id = client_id
    sprint.sprint_status = status
    sprint.max_spend_usd = max_spend_usd
    sprint.spent_usd = spent_usd
    sprint.max_videos = max_videos
    return sprint


def _mock_asset(job_id: str = "gen-123") -> MagicMock:
    asset = MagicMock()
    asset.id = "00000000-0000-0000-0000-000000000020"
    asset.provider_job_id = job_id
    return asset


def _mock_adapter(
    estimated_usd: float = 0.06,
    job_id: str = "gen-123",
) -> MagicMock:
    adapter = MagicMock()
    adapter.estimate_cost = AsyncMock(return_value=CostEstimate(estimated_usd=estimated_usd, uncertain=True))
    adapter.generate_video = AsyncMock(return_value=GenerationResult(job_id=job_id, status="queued"))
    return adapter


# ---------------------------------------------------------------------------
# helpers to build session mock
# ---------------------------------------------------------------------------


def _session_ctx(sprint: MagicMock, asset: MagicMock, video_count: int = 0) -> MagicMock:
    session = AsyncMock()
    session.get = AsyncMock(return_value=sprint)
    scalar = MagicMock()
    scalar.scalar_one = MagicMock(return_value=video_count)
    session.execute = AsyncMock(return_value=scalar)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, "id", asset.id))

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_api_video_success() -> None:
    sprint = _mock_sprint()
    asset = _mock_asset()
    adapter = _mock_adapter()

    with (
        patch(_GUARD),
        patch(_GET_ADAPTER, return_value=adapter),
        patch(_GET_SESSION, return_value=_session_ctx(sprint, asset)),
        patch(_SET_TENANT, new_callable=AsyncMock),
    ):
        result = await request_api_video(_input())

    assert result.status == "queued"
    assert result.job_id == "gen-123"
    assert result.sprint_id == "00000000-0000-0000-0000-000000000010"
    assert result.estimated_cost_usd == 0.06
    assert result.next_action == "get_video_job_status"
    adapter.generate_video.assert_awaited_once()


@pytest.mark.asyncio
async def test_request_api_video_updates_sprint_spent_usd() -> None:
    sprint = _mock_sprint(spent_usd=1.0)
    adapter = _mock_adapter(estimated_usd=0.06)

    with (
        patch(_GUARD),
        patch(_GET_ADAPTER, return_value=adapter),
        patch(_GET_SESSION, return_value=_session_ctx(sprint, _mock_asset())),
        patch(_SET_TENANT, new_callable=AsyncMock),
    ):
        await request_api_video(_input())

    assert abs(sprint.spent_usd - 1.06) < 1e-9


# ---------------------------------------------------------------------------
# guard failures
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sprint_not_found_raises() -> None:
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.execute = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(_GUARD),
        patch(_GET_ADAPTER, return_value=_mock_adapter()),
        patch(_GET_SESSION, return_value=ctx),
        patch(_SET_TENANT, new_callable=AsyncMock),
        pytest.raises(VosError) as exc_info,
    ):
        await request_api_video(_input())

    assert exc_info.value.error_code == ErrorCode.NOT_FOUND


@pytest.mark.asyncio
async def test_sprint_wrong_client_raises() -> None:
    sprint = _mock_sprint(client_id="00000000-0000-0000-0000-000000000099")

    with (
        patch(_GUARD),
        patch(_GET_ADAPTER, return_value=_mock_adapter()),
        patch(_GET_SESSION, return_value=_session_ctx(sprint, _mock_asset())),
        patch(_SET_TENANT, new_callable=AsyncMock),
        pytest.raises(VosError) as exc_info,
    ):
        await request_api_video(_input())

    assert exc_info.value.error_code == ErrorCode.INVALID_INPUT


@pytest.mark.asyncio
async def test_closed_sprint_raises() -> None:
    sprint = _mock_sprint(status="closed")

    with (
        patch(_GUARD),
        patch(_GET_ADAPTER, return_value=_mock_adapter()),
        patch(_GET_SESSION, return_value=_session_ctx(sprint, _mock_asset())),
        patch(_SET_TENANT, new_callable=AsyncMock),
        pytest.raises(VosError) as exc_info,
    ):
        await request_api_video(_input())

    assert exc_info.value.error_code == ErrorCode.SPRINT_CLOSED


@pytest.mark.asyncio
async def test_budget_exceeded_raises() -> None:
    sprint = _mock_sprint(max_spend_usd=0.05, spent_usd=0.04)

    with (
        patch(_GUARD),
        patch(_GET_ADAPTER, return_value=_mock_adapter(estimated_usd=0.06)),
        patch(_GET_SESSION, return_value=_session_ctx(sprint, _mock_asset())),
        patch(_SET_TENANT, new_callable=AsyncMock),
        pytest.raises(VosError) as exc_info,
    ):
        await request_api_video(_input())

    assert exc_info.value.error_code == ErrorCode.BUDGET_EXCEEDED


@pytest.mark.asyncio
async def test_max_videos_limit_reached_raises() -> None:
    sprint = _mock_sprint(max_videos=2)

    with (
        patch(_GUARD),
        patch(_GET_ADAPTER, return_value=_mock_adapter()),
        patch(_GET_SESSION, return_value=_session_ctx(sprint, _mock_asset(), video_count=2)),
        patch(_SET_TENANT, new_callable=AsyncMock),
        pytest.raises(VosError) as exc_info,
    ):
        await request_api_video(_input())

    assert exc_info.value.error_code == ErrorCode.BUDGET_EXCEEDED


@pytest.mark.asyncio
async def test_max_videos_not_reached_succeeds() -> None:
    sprint = _mock_sprint(max_videos=3)

    with (
        patch(_GUARD),
        patch(_GET_ADAPTER, return_value=_mock_adapter()),
        patch(_GET_SESSION, return_value=_session_ctx(sprint, _mock_asset(), video_count=2)),
        patch(_SET_TENANT, new_callable=AsyncMock),
    ):
        result = await request_api_video(_input())

    assert result.status == "queued"


# ---------------------------------------------------------------------------
# schema validation
# ---------------------------------------------------------------------------


def test_api_video_input_requires_prompt() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ApiVideoInput(
            sprint_id="spr-1",
            client_id="cli-1",
            prompt="",
            prompt_version="v1",
            preset_version="p1",
            approval_token="tok",
        )


def test_api_video_input_requires_approval_token() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ApiVideoInput(
            sprint_id="spr-1",
            client_id="cli-1",
            prompt="a prompt",
            prompt_version="v1",
            preset_version="p1",
            approval_token="",
        )


def test_api_video_input_valid_defaults() -> None:
    data = _input()
    assert data.resolution == "720p"
    assert data.duration_seconds == 5
    assert data.aspect_ratio == "16:9"
    assert data.image_url is None
