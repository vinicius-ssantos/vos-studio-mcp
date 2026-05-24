"""Unit tests for list_video_jobs service (Issue #31)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.services.generation_service import list_video_jobs

_GUARD = "vos_studio_mcp.services.generation_service.assert_owns_client"
_GET_SESSION = "vos_studio_mcp.services.generation_service.get_session"
_SET_TENANT = "vos_studio_mcp.services.generation_service.set_tenant_context"

_SPRINT_ID = "00000000-0000-0000-0000-000000000010"
_CLIENT_ID = "00000000-0000-0000-0000-000000000001"
_MISSING = object()  # sentinel: distinguishes "use default" from "return None"


def _mock_asset(
    gen_status: str = "completed",
    storage_status: str = "stored",
    storage_url: str | None = "https://r2.example.com/vid.mp4",
) -> MagicMock:
    a = MagicMock()
    a.id = "aaaaaaaa-0000-0000-0000-000000000001"
    a.provider_job_id = "job-123"
    a.generation_status = gen_status
    a.storage_status = storage_status
    a.storage_url = storage_url
    a.created_at = MagicMock()
    return a


def _mock_sprint(client_id: str = _CLIENT_ID) -> MagicMock:
    s = MagicMock()
    s.client_id = client_id
    return s


def _session_ctx(sprint: MagicMock | None | object = _MISSING, assets: list[MagicMock] | None = None) -> MagicMock:
    if assets is None:
        assets = []

    scalars = MagicMock()
    scalars.all = MagicMock(return_value=assets)
    execute_result = MagicMock()
    execute_result.scalars = MagicMock(return_value=scalars)

    session = AsyncMock()
    session.get = AsyncMock(return_value=_mock_sprint() if sprint is _MISSING else sprint)
    session.execute = AsyncMock(return_value=execute_result)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


class TestListVideoJobs:
    @pytest.mark.asyncio
    async def test_returns_jobs_and_counts(self) -> None:
        assets = [
            _mock_asset("completed", "stored", "https://r2.example.com/a.mp4"),
            _mock_asset("processing", "not_required", None),
            _mock_asset("failed", "failed", None),
        ]
        ctx = _session_ctx(assets=assets)

        with patch(_GUARD), patch(_GET_SESSION, return_value=ctx), patch(_SET_TENANT):  # noqa: SIM117
            resp = await list_video_jobs(_SPRINT_ID, _CLIENT_ID)

        assert resp.status == "ok"
        assert resp.sprint_id == _SPRINT_ID
        assert len(resp.jobs) == 3
        assert resp.summary.total == 3
        assert resp.summary.completed == 1
        assert resp.summary.processing == 1
        assert resp.summary.failed == 1
        assert resp.summary.pending == 0

    @pytest.mark.asyncio
    async def test_next_action_poll_again_when_processing(self) -> None:
        assets = [_mock_asset("processing", "not_required", None)]
        ctx = _session_ctx(assets=assets)

        with patch(_GUARD), patch(_GET_SESSION, return_value=ctx), patch(_SET_TENANT):  # noqa: SIM117
            resp = await list_video_jobs(_SPRINT_ID, _CLIENT_ID)

        assert resp.next_action == "poll_again"

    @pytest.mark.asyncio
    async def test_next_action_prepare_dashboard_pack_when_all_done(self) -> None:
        assets = [_mock_asset("completed"), _mock_asset("completed")]
        ctx = _session_ctx(assets=assets)

        with patch(_GUARD), patch(_GET_SESSION, return_value=ctx), patch(_SET_TENANT):  # noqa: SIM117
            resp = await list_video_jobs(_SPRINT_ID, _CLIENT_ID)

        assert resp.next_action == "prepare_dashboard_pack"

    @pytest.mark.asyncio
    async def test_next_action_request_api_video_when_empty(self) -> None:
        ctx = _session_ctx(assets=[])

        with patch(_GUARD), patch(_GET_SESSION, return_value=ctx), patch(_SET_TENANT):  # noqa: SIM117
            resp = await list_video_jobs(_SPRINT_ID, _CLIENT_ID)

        assert resp.next_action == "request_api_video"
        assert resp.summary.total == 0

    @pytest.mark.asyncio
    async def test_raises_not_found_when_sprint_missing(self) -> None:
        ctx = _session_ctx(sprint=None)

        with patch(_GUARD), patch(_GET_SESSION, return_value=ctx), patch(_SET_TENANT):  # noqa: SIM117
            with pytest.raises(VosError) as exc_info:
                await list_video_jobs(_SPRINT_ID, _CLIENT_ID)

        assert exc_info.value.error_code == ErrorCode.NOT_FOUND

    @pytest.mark.asyncio
    async def test_raises_invalid_input_when_wrong_client(self) -> None:
        sprint = _mock_sprint(client_id="other-client-id")
        ctx = _session_ctx(sprint=sprint)

        with patch(_GUARD), patch(_GET_SESSION, return_value=ctx), patch(_SET_TENANT):  # noqa: SIM117
            with pytest.raises(VosError) as exc_info:
                await list_video_jobs(_SPRINT_ID, _CLIENT_ID)

        assert exc_info.value.error_code == ErrorCode.INVALID_INPUT

    @pytest.mark.asyncio
    async def test_job_fields_are_mapped_correctly(self) -> None:
        asset = _mock_asset("completed", "stored", "https://r2.example.com/vid.mp4")
        ctx = _session_ctx(assets=[asset])

        with patch(_GUARD), patch(_GET_SESSION, return_value=ctx), patch(_SET_TENANT):  # noqa: SIM117
            resp = await list_video_jobs(_SPRINT_ID, _CLIENT_ID)

        job = resp.jobs[0]
        assert job.generation_status == "completed"
        assert job.storage_status == "stored"
        assert job.storage_url == "https://r2.example.com/vid.mp4"
        assert job.provider_job_id == "job-123"


class TestListVideoJobsToolLayer:
    def test_tool_registered(self) -> None:
        from tests.tools.test_tools_layer import _EXPECTED_TOOLS
        assert "list_video_jobs" in _EXPECTED_TOOLS
