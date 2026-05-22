"""Unit tests for Higgsfield provider adapter."""

import hashlib
import hmac
from typing import Any
from unittest.mock import patch

import pytest
import respx
from httpx import Response

from vos_studio_mcp.config.env import Settings
from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.services.providers.base import GenerationParams
from vos_studio_mcp.services.providers.higgsfield import HiggsFieldAdapter

_PATCH = "vos_studio_mcp.services.providers.higgsfield.get_settings"


def _settings(**kwargs: Any) -> Settings:
    return Settings(HIGGSFIELD_API_KEY="test-key", WEBHOOK_SECRET_HIGGSFIELD="wh-secret", **kwargs)


@pytest.fixture
def adapter() -> HiggsFieldAdapter:
    return HiggsFieldAdapter()


@pytest.fixture
def params() -> GenerationParams:
    return GenerationParams(
        sprint_id="spr-abc",
        prompt_version="v1",
        preset_version="p1",
        mode="api_credits",
        approval_token="tok-approved",
        prompt="A cinematic product launch video",
        resolution="720p",
        duration_seconds=5,
        aspect_ratio="16:9",
    )


# ---------------------------------------------------------------------------
# estimate_cost
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_estimate_cost_known_combination(
    adapter: HiggsFieldAdapter, params: GenerationParams
) -> None:
    result = await adapter.estimate_cost(params)
    assert result.estimated_usd == 0.06
    assert result.uncertain is True


@pytest.mark.asyncio
async def test_estimate_cost_unknown_combination(
    adapter: HiggsFieldAdapter, params: GenerationParams
) -> None:
    params.resolution = "4k"
    result = await adapter.estimate_cost(params)
    assert result.estimated_usd == 0.10
    assert result.uncertain is True


@pytest.mark.asyncio
async def test_estimate_cost_1080p_10s(
    adapter: HiggsFieldAdapter, params: GenerationParams
) -> None:
    params.resolution = "1080p"
    params.duration_seconds = 10
    result = await adapter.estimate_cost(params)
    assert result.estimated_usd == 0.20


# ---------------------------------------------------------------------------
# generate_image — must raise
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_image_raises(
    adapter: HiggsFieldAdapter, params: GenerationParams
) -> None:
    with pytest.raises(NotImplementedError):
        await adapter.generate_image(params)


# ---------------------------------------------------------------------------
# generate_video — no API key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_video_no_api_key_raises(
    adapter: HiggsFieldAdapter, params: GenerationParams
) -> None:
    with patch(_PATCH, return_value=Settings(HIGGSFIELD_API_KEY="")), pytest.raises(VosError) as exc_info:
        await adapter.generate_video(params)
    assert exc_info.value.error_code == ErrorCode.PROVIDER_ERROR


@pytest.mark.asyncio
async def test_generate_video_no_approval_token_raises(
    adapter: HiggsFieldAdapter, params: GenerationParams
) -> None:
    params.approval_token = None
    with patch(_PATCH, return_value=_settings()), pytest.raises(VosError) as exc_info:
        await adapter.generate_video(params)
    assert exc_info.value.error_code == ErrorCode.INVALID_INPUT


# ---------------------------------------------------------------------------
# generate_video — text2video (no image_url)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_generate_video_text2video_success(
    adapter: HiggsFieldAdapter, params: GenerationParams
) -> None:
    respx.post("https://api.higgsfield.ai/v1/video/generate").mock(
        return_value=Response(200, json={"generation_id": "gen-123", "request_id": "req-456"})
    )
    with patch(_PATCH, return_value=_settings()):
        result = await adapter.generate_video(params)

    assert result.job_id == "gen-123"
    assert result.status == "queued"


@pytest.mark.asyncio
@respx.mock
async def test_generate_video_falls_back_to_request_id(
    adapter: HiggsFieldAdapter, params: GenerationParams
) -> None:
    respx.post("https://api.higgsfield.ai/v1/video/generate").mock(
        return_value=Response(200, json={"request_id": "req-789"})
    )
    with patch(_PATCH, return_value=_settings()):
        result = await adapter.generate_video(params)

    assert result.job_id == "req-789"


# ---------------------------------------------------------------------------
# generate_video — image2video
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_generate_video_image2video_uses_dop_endpoint(
    adapter: HiggsFieldAdapter, params: GenerationParams
) -> None:
    params.image_url = "https://example.com/ref.jpg"
    route = respx.post("https://api.higgsfield.ai/v1/image2video/dop").mock(
        return_value=Response(200, json={"generation_id": "gen-dop-001"})
    )
    with patch(_PATCH, return_value=_settings()):
        result = await adapter.generate_video(params)

    assert route.called
    assert result.job_id == "gen-dop-001"


# ---------------------------------------------------------------------------
# generate_video — error codes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_generate_video_402_raises_budget_exceeded(
    adapter: HiggsFieldAdapter, params: GenerationParams
) -> None:
    respx.post("https://api.higgsfield.ai/v1/video/generate").mock(
        return_value=Response(402, json={"error": "insufficient credits"})
    )
    with patch(_PATCH, return_value=_settings()), pytest.raises(VosError) as exc_info:
        await adapter.generate_video(params)
    assert exc_info.value.error_code == ErrorCode.BUDGET_EXCEEDED


@pytest.mark.asyncio
@respx.mock
async def test_generate_video_401_raises_provider_error(
    adapter: HiggsFieldAdapter, params: GenerationParams
) -> None:
    respx.post("https://api.higgsfield.ai/v1/video/generate").mock(
        return_value=Response(401, json={"error": "unauthorized"})
    )
    with patch(_PATCH, return_value=_settings()), pytest.raises(VosError) as exc_info:
        await adapter.generate_video(params)
    assert exc_info.value.error_code == ErrorCode.PROVIDER_ERROR


@pytest.mark.asyncio
@respx.mock
async def test_generate_video_500_raises_provider_error(
    adapter: HiggsFieldAdapter, params: GenerationParams
) -> None:
    respx.post("https://api.higgsfield.ai/v1/video/generate").mock(
        return_value=Response(500, json={"error": "internal error"})
    )
    with patch(_PATCH, return_value=_settings()), pytest.raises(VosError) as exc_info:
        await adapter.generate_video(params)
    assert exc_info.value.error_code == ErrorCode.PROVIDER_ERROR


# ---------------------------------------------------------------------------
# check_job_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_check_job_status_queued(adapter: HiggsFieldAdapter) -> None:
    respx.get("https://api.higgsfield.ai/v1/video/status/gen-123").mock(
        return_value=Response(200, json={"status": "QUEUED"})
    )
    with patch(_PATCH, return_value=_settings()):
        result = await adapter.check_job_status("gen-123")

    assert result.job_id == "gen-123"
    assert result.status == "queued"
    assert result.error is None


@pytest.mark.asyncio
@respx.mock
async def test_check_job_status_processing(adapter: HiggsFieldAdapter) -> None:
    respx.get("https://api.higgsfield.ai/v1/video/status/gen-123").mock(
        return_value=Response(200, json={"status": "PROCESSING"})
    )
    with patch(_PATCH, return_value=_settings()):
        result = await adapter.check_job_status("gen-123")

    assert result.status == "running"


@pytest.mark.asyncio
@respx.mock
async def test_check_job_status_completed(adapter: HiggsFieldAdapter) -> None:
    respx.get("https://api.higgsfield.ai/v1/video/status/gen-123").mock(
        return_value=Response(
            200,
            json={
                "status": "COMPLETED",
                "output": {
                    "media_url": "https://cdn.higgsfield.ai/video.mp4",
                    "media_type": "video",
                },
            },
        )
    )
    with patch(_PATCH, return_value=_settings()):
        result = await adapter.check_job_status("gen-123")

    assert result.status == "completed"
    assert result.error is None


@pytest.mark.asyncio
@respx.mock
async def test_check_job_status_failed_with_error_message(adapter: HiggsFieldAdapter) -> None:
    respx.get("https://api.higgsfield.ai/v1/video/status/gen-123").mock(
        return_value=Response(
            200, json={"status": "FAILED", "error": "content policy violation"}
        )
    )
    with patch(_PATCH, return_value=_settings()):
        result = await adapter.check_job_status("gen-123")

    assert result.status == "failed"
    assert result.error == "content policy violation"


@pytest.mark.asyncio
@respx.mock
async def test_check_job_status_error_maps_to_failed(adapter: HiggsFieldAdapter) -> None:
    respx.get("https://api.higgsfield.ai/v1/video/status/gen-123").mock(
        return_value=Response(200, json={"status": "ERROR", "message": "timeout"})
    )
    with patch(_PATCH, return_value=_settings()):
        result = await adapter.check_job_status("gen-123")

    assert result.status == "failed"
    assert result.error == "timeout"


@pytest.mark.asyncio
@respx.mock
async def test_check_job_status_http_error_raises(adapter: HiggsFieldAdapter) -> None:
    respx.get("https://api.higgsfield.ai/v1/video/status/gen-bad").mock(
        return_value=Response(404, json={"error": "not found"})
    )
    with patch(_PATCH, return_value=_settings()), pytest.raises(VosError) as exc_info:
        await adapter.check_job_status("gen-bad")
    assert exc_info.value.error_code == ErrorCode.PROVIDER_ERROR


@pytest.mark.asyncio
async def test_check_job_status_no_api_key_raises(adapter: HiggsFieldAdapter) -> None:
    with patch(_PATCH, return_value=Settings(HIGGSFIELD_API_KEY="")), pytest.raises(VosError) as exc_info:
        await adapter.check_job_status("gen-123")
    assert exc_info.value.error_code == ErrorCode.PROVIDER_ERROR


# ---------------------------------------------------------------------------
# prepare_manual_pack
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prepare_manual_pack_returns_valid_pack(
    adapter: HiggsFieldAdapter, params: GenerationParams
) -> None:
    pack = await adapter.prepare_manual_pack(params)
    assert pack.provider == "higgsfield"
    assert pack.model == "dop"
    assert pack.prompt == "A cinematic product launch video"
    assert "spr-abc" in pack.naming_convention
    assert len(pack.checklist) > 0
    assert len(pack.qa_criteria) > 0
    assert "720p" in pack.checklist[2]
    assert "5s" in pack.checklist[2]


@pytest.mark.asyncio
async def test_prepare_manual_pack_falls_back_to_prompt_version(
    adapter: HiggsFieldAdapter, params: GenerationParams
) -> None:
    params.prompt = ""
    pack = await adapter.prepare_manual_pack(params)
    assert pack.prompt == "v1"


# ---------------------------------------------------------------------------
# verify_webhook_signature
# ---------------------------------------------------------------------------


def _make_sig(secret: str, payload: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def test_verify_webhook_valid_signature(adapter: HiggsFieldAdapter) -> None:
    payload = b'{"event":"generation.completed","generation_id":"gen-123"}'
    headers = {"X-Higgsfield-Signature": _make_sig("wh-secret", payload)}
    with patch(_PATCH, return_value=_settings()):
        assert adapter.verify_webhook_signature(payload, headers) is True


def test_verify_webhook_invalid_signature(adapter: HiggsFieldAdapter) -> None:
    payload = b'{"event":"generation.completed"}'
    headers = {"X-Higgsfield-Signature": "sha256=deadbeef"}
    with patch(_PATCH, return_value=_settings()):
        assert adapter.verify_webhook_signature(payload, headers) is False


def test_verify_webhook_lowercase_header(adapter: HiggsFieldAdapter) -> None:
    payload = b'{"event":"test"}'
    headers = {"x-higgsfield-signature": _make_sig("wh-secret", payload)}
    with patch(_PATCH, return_value=_settings()):
        assert adapter.verify_webhook_signature(payload, headers) is True


def test_verify_webhook_no_secret_rejects(adapter: HiggsFieldAdapter) -> None:
    payload = b'{"event":"test"}'
    headers = {"X-Higgsfield-Signature": "sha256=anything"}
    with patch(_PATCH, return_value=Settings(WEBHOOK_SECRET_HIGGSFIELD="")):
        assert adapter.verify_webhook_signature(payload, headers) is False


def test_verify_webhook_missing_header_rejects(adapter: HiggsFieldAdapter) -> None:
    payload = b'{"event":"test"}'
    with patch(_PATCH, return_value=_settings()):
        assert adapter.verify_webhook_signature(payload, {}) is False


def test_verify_webhook_sig_without_prefix(adapter: HiggsFieldAdapter) -> None:
    payload = b'{"event":"test"}'
    raw_sig = hmac.new(b"wh-secret", payload, hashlib.sha256).hexdigest()
    headers = {"X-Higgsfield-Signature": raw_sig}
    with patch(_PATCH, return_value=_settings()):
        assert adapter.verify_webhook_signature(payload, headers) is True
