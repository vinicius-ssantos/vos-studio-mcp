"""Unit tests for HiggsFieldMcpAdapter (ADR-0044, Issue #73 Phase 3)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_SERVICE = "vos_studio_mcp.services.providers.higgsfield_mcp"
_CLIENT = "vos_studio_mcp.services.mcp_clients.higgsfield"
_SETTINGS = f"{_SERVICE}.get_settings"

_SPRINT_ID = "00000000-0000-0000-0000-000000000010"


def _settings(*, enabled: bool = True, token: str = "tok") -> MagicMock:
    s = MagicMock()
    s.higgsfield_mcp_enabled = enabled
    s.higgsfield_mcp_access_token = token
    return s


def _params(*, image_url: str | None = None, approval_token: str | None = "appr-token") -> MagicMock:
    from vos_studio_mcp.services.providers.base import GenerationParams

    return GenerationParams(
        sprint_id=_SPRINT_ID,
        prompt_version="v1",
        preset_version="p1",
        mode="api_credits",
        approval_token=approval_token,
        prompt="A cinematic hero shot",
        image_url=image_url,
        duration_seconds=5,
        resolution="720p",
        aspect_ratio="16:9",
    )


# ---------------------------------------------------------------------------
# estimate_cost
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_estimate_cost_returns_cost_for_known_resolution() -> None:
    from vos_studio_mcp.services.providers.higgsfield_mcp import HiggsFieldMcpAdapter

    adapter = HiggsFieldMcpAdapter()
    estimate = await adapter.estimate_cost(_params())

    assert estimate.estimated_usd == pytest.approx(0.06)
    assert estimate.uncertain is True


@pytest.mark.asyncio
async def test_estimate_cost_returns_default_for_unknown_combo() -> None:
    from vos_studio_mcp.services.providers.base import GenerationParams
    from vos_studio_mcp.services.providers.higgsfield_mcp import HiggsFieldMcpAdapter

    adapter = HiggsFieldMcpAdapter()
    params = GenerationParams(
        sprint_id=_SPRINT_ID,
        prompt_version="v1",
        preset_version="p1",
        mode="api_credits",
        approval_token="tok",
        resolution="4K",
        duration_seconds=30,
    )
    estimate = await adapter.estimate_cost(params)
    assert estimate.estimated_usd == pytest.approx(0.10)
    assert estimate.uncertain is True


# ---------------------------------------------------------------------------
# generate_video
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_video_disabled_raises() -> None:
    from vos_studio_mcp.errors import ErrorCode, VosError
    from vos_studio_mcp.services.providers.higgsfield_mcp import HiggsFieldMcpAdapter

    with patch(_SETTINGS, return_value=_settings(enabled=False)), pytest.raises(VosError) as exc:
        await HiggsFieldMcpAdapter().generate_video(_params())

    assert exc.value.error_code == ErrorCode.PROVIDER_ERROR


@pytest.mark.asyncio
async def test_generate_video_missing_token_raises() -> None:
    from vos_studio_mcp.errors import ErrorCode, VosError
    from vos_studio_mcp.services.providers.higgsfield_mcp import HiggsFieldMcpAdapter

    with patch(_SETTINGS, return_value=_settings(token="")), pytest.raises(VosError) as exc:
        await HiggsFieldMcpAdapter().generate_video(_params())

    assert exc.value.error_code == ErrorCode.PROVIDER_ERROR


@pytest.mark.asyncio
async def test_generate_video_missing_approval_token_raises() -> None:
    from vos_studio_mcp.errors import ErrorCode, VosError
    from vos_studio_mcp.services.providers.higgsfield_mcp import HiggsFieldMcpAdapter

    with patch(_SETTINGS, return_value=_settings()), pytest.raises(VosError) as exc:
        await HiggsFieldMcpAdapter().generate_video(_params(approval_token=None))

    assert exc.value.error_code == ErrorCode.INVALID_INPUT


@pytest.mark.asyncio
async def test_generate_video_returns_job_id() -> None:
    from vos_studio_mcp.services.providers.higgsfield_mcp import HiggsFieldMcpAdapter

    with (
        patch(_SETTINGS, return_value=_settings()),
        patch(
            f"{_SERVICE}.call_tool",
            new=AsyncMock(return_value={"generation_id": "job-abc"}),
        ),
    ):
        result = await HiggsFieldMcpAdapter().generate_video(_params())

    assert result.job_id == "job-abc"
    assert result.status == "queued"


@pytest.mark.asyncio
async def test_generate_video_calls_image_to_video_tool_when_image_url_set() -> None:
    from vos_studio_mcp.services.providers.higgsfield_mcp import HiggsFieldMcpAdapter

    mock_call = AsyncMock(return_value={"generation_id": "job-xyz"})
    with patch(_SETTINGS, return_value=_settings()), patch(f"{_SERVICE}.call_tool", new=mock_call):
        await HiggsFieldMcpAdapter().generate_video(_params(image_url="https://example.com/img.jpg"))

    tool_name = mock_call.call_args[0][0]
    assert tool_name == "generate_image_to_video"
    assert mock_call.call_args[0][1]["image_url"] == "https://example.com/img.jpg"


@pytest.mark.asyncio
async def test_generate_video_raises_when_no_job_id_returned() -> None:
    from vos_studio_mcp.errors import ErrorCode, VosError
    from vos_studio_mcp.services.providers.higgsfield_mcp import HiggsFieldMcpAdapter

    with (
        patch(_SETTINGS, return_value=_settings()),
        patch(f"{_SERVICE}.call_tool", new=AsyncMock(return_value={})),
        pytest.raises(VosError) as exc,
    ):
        await HiggsFieldMcpAdapter().generate_video(_params())

    assert exc.value.error_code == ErrorCode.PROVIDER_ERROR


# ---------------------------------------------------------------------------
# check_job_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_job_status_completed_returns_media_url() -> None:
    from vos_studio_mcp.services.providers.higgsfield_mcp import HiggsFieldMcpAdapter

    tool_result = {
        "status": "COMPLETED",
        "output": {"media_url": "https://cdn.higgsfield.ai/video.mp4"},
    }
    with (
        patch(_SETTINGS, return_value=_settings()),
        patch(f"{_SERVICE}.call_tool", new=AsyncMock(return_value=tool_result)),
    ):
        status = await HiggsFieldMcpAdapter().check_job_status("job-abc")

    assert status.status == "completed"
    assert status.media_url == "https://cdn.higgsfield.ai/video.mp4"
    assert status.error is None


@pytest.mark.asyncio
async def test_check_job_status_running_returns_running() -> None:
    from vos_studio_mcp.services.providers.higgsfield_mcp import HiggsFieldMcpAdapter

    with (
        patch(_SETTINGS, return_value=_settings()),
        patch(
            f"{_SERVICE}.call_tool",
            new=AsyncMock(return_value={"status": "PROCESSING"}),
        ),
    ):
        status = await HiggsFieldMcpAdapter().check_job_status("job-abc")

    assert status.status == "running"
    assert status.media_url is None


@pytest.mark.asyncio
async def test_check_job_status_failed_returns_error_message() -> None:
    from vos_studio_mcp.services.providers.higgsfield_mcp import HiggsFieldMcpAdapter

    with (
        patch(_SETTINGS, return_value=_settings()),
        patch(
            f"{_SERVICE}.call_tool",
            new=AsyncMock(return_value={"status": "FAILED", "error": "prompt rejected"}),
        ),
    ):
        status = await HiggsFieldMcpAdapter().check_job_status("job-abc")

    assert status.status == "failed"
    assert status.error == "prompt rejected"


@pytest.mark.asyncio
async def test_check_job_status_passes_job_id_to_tool() -> None:
    from vos_studio_mcp.services.providers.higgsfield_mcp import HiggsFieldMcpAdapter

    mock_call = AsyncMock(return_value={"status": "QUEUED"})
    with patch(_SETTINGS, return_value=_settings()), patch(f"{_SERVICE}.call_tool", new=mock_call):
        await HiggsFieldMcpAdapter().check_job_status("job-def")

    assert mock_call.call_args[0][0] == "job_display"
    assert mock_call.call_args[0][1] == {"generation_id": "job-def"}


# ---------------------------------------------------------------------------
# verify_webhook_signature
# ---------------------------------------------------------------------------


def test_verify_webhook_signature_always_returns_false() -> None:
    from vos_studio_mcp.services.providers.higgsfield_mcp import HiggsFieldMcpAdapter

    assert HiggsFieldMcpAdapter().verify_webhook_signature(b"payload", {}) is False


# ---------------------------------------------------------------------------
# call_tool integration (mcp_client module)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_tool_disabled_raises_vos_error() -> None:
    from vos_studio_mcp.errors import ErrorCode, VosError
    from vos_studio_mcp.services.mcp_clients.higgsfield import call_tool

    with patch(
        "vos_studio_mcp.services.mcp_clients.higgsfield.get_settings",
        return_value=_settings(enabled=False),
    ), pytest.raises(VosError) as exc:
        await call_tool("generate_video", {})

    assert exc.value.error_code == ErrorCode.PROVIDER_ERROR


@pytest.mark.asyncio
async def test_call_tool_missing_token_raises_vos_error() -> None:
    from vos_studio_mcp.errors import ErrorCode, VosError
    from vos_studio_mcp.services.mcp_clients.higgsfield import call_tool

    with patch(
        "vos_studio_mcp.services.mcp_clients.higgsfield.get_settings",
        return_value=_settings(token=""),
    ), pytest.raises(VosError) as exc:
        await call_tool("generate_video", {})

    assert exc.value.error_code == ErrorCode.PROVIDER_ERROR


@pytest.mark.asyncio
async def test_call_tool_json_rpc_error_raises_vos_error() -> None:
    """A JSON-RPC error object in the response raises VosError."""
    from unittest.mock import MagicMock

    import httpx

    from vos_studio_mcp.errors import ErrorCode, VosError
    from vos_studio_mcp.services.mcp_clients.higgsfield import call_tool

    def _resp(status: int, body: dict) -> MagicMock:
        r = MagicMock(spec=httpx.Response)
        r.status_code = status
        r.is_success = 200 <= status < 300
        r.headers = {}
        r.json = MagicMock(return_value=body)
        r.text = ""
        return r

    client = AsyncMock()
    client.post = AsyncMock(
        side_effect=[
            _resp(200, {"jsonrpc": "2.0", "id": 1, "result": {"serverInfo": {}, "capabilities": {"tools": {}}}}),
            _resp(200, {}),  # notifications/initialized
            _resp(200, {"jsonrpc": "2.0", "id": 2, "error": {"code": -32600, "message": "invalid request"}}),
        ]
    )
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)

    s = _settings()
    with (
        patch("vos_studio_mcp.services.mcp_clients.higgsfield.get_settings", return_value=s),
        patch("vos_studio_mcp.services.mcp_clients.higgsfield.httpx.AsyncClient", return_value=ctx),
        pytest.raises(VosError) as exc,
    ):
        await call_tool("generate_video", {})

    assert exc.value.error_code == ErrorCode.PROVIDER_ERROR
    assert "invalid request" in str(exc.value)


@pytest.mark.asyncio
async def test_call_tool_success_returns_parsed_content() -> None:
    import json as _json

    import httpx

    from vos_studio_mcp.services.mcp_clients.higgsfield import call_tool

    content_text = _json.dumps({"generation_id": "job-001"})

    def _resp(status: int, body: dict) -> MagicMock:
        r = MagicMock(spec=httpx.Response)
        r.status_code = status
        r.is_success = 200 <= status < 300
        r.headers = {}
        r.json = MagicMock(return_value=body)
        r.text = ""
        return r

    client = AsyncMock()
    client.post = AsyncMock(
        side_effect=[
            _resp(200, {"jsonrpc": "2.0", "id": 1, "result": {"serverInfo": {}, "capabilities": {"tools": {}}}}),
            _resp(200, {}),
            _resp(200, {"jsonrpc": "2.0", "id": 2, "result": {"content": [{"type": "text", "text": content_text}]}}),
        ]
    )
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)

    s = _settings()
    with (
        patch("vos_studio_mcp.services.mcp_clients.higgsfield.get_settings", return_value=s),
        patch("vos_studio_mcp.services.mcp_clients.higgsfield.httpx.AsyncClient", return_value=ctx),
    ):
        result = await call_tool("generate_video", {"prompt": "test"})

    assert result == {"generation_id": "job-001"}
