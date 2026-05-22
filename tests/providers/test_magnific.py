"""Unit tests for Magnific upscaling provider adapter (ADR-0009)."""

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
from vos_studio_mcp.services.providers.magnific import MagnificAdapter

_PATCH = "vos_studio_mcp.services.providers.magnific.get_settings"


def _settings(**kwargs: Any) -> Settings:
    return Settings(
        MAGNIFIC_API_KEY="mag-test-key", WEBHOOK_SECRET_MAGNIFIC="mag-secret", **kwargs
    )


@pytest.fixture
def adapter() -> MagnificAdapter:
    return MagnificAdapter()


@pytest.fixture
def params() -> GenerationParams:
    return GenerationParams(
        sprint_id="spr-mag-001",
        prompt_version="v1",
        preset_version="p1",
        mode="api_credits",
        approval_token="tok-approved",
        prompt="",
        image_url="https://cdn.example.com/source.jpg",
        resolution="720p",
        duration_seconds=5,
        aspect_ratio="16:9",
    )


# ---------------------------------------------------------------------------
# estimate_cost
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_estimate_cost(adapter: MagnificAdapter, params: GenerationParams) -> None:
    result = await adapter.estimate_cost(params)
    assert result.estimated_usd == 0.05
    assert result.uncertain is False


# ---------------------------------------------------------------------------
# generate_image (upscaling)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_image_no_api_key_raises(
    adapter: MagnificAdapter, params: GenerationParams
) -> None:
    with patch(_PATCH, return_value=Settings(MAGNIFIC_API_KEY="")), pytest.raises(VosError) as exc:
        await adapter.generate_image(params)
    assert exc.value.error_code == ErrorCode.PROVIDER_ERROR


@pytest.mark.asyncio
async def test_generate_image_no_image_url_raises(
    adapter: MagnificAdapter, params: GenerationParams
) -> None:
    params.image_url = None
    with patch(_PATCH, return_value=_settings()), pytest.raises(VosError) as exc:
        await adapter.generate_image(params)
    assert exc.value.error_code == ErrorCode.INVALID_INPUT


@pytest.mark.asyncio
async def test_generate_image_no_approval_token_raises(
    adapter: MagnificAdapter, params: GenerationParams
) -> None:
    params.approval_token = None
    with patch(_PATCH, return_value=_settings()), pytest.raises(VosError) as exc:
        await adapter.generate_image(params)
    assert exc.value.error_code == ErrorCode.INVALID_INPUT


@pytest.mark.asyncio
@respx.mock
async def test_generate_image_success(
    adapter: MagnificAdapter, params: GenerationParams
) -> None:
    respx.post("https://api.magnific.ai/v1/upscaling").mock(
        return_value=Response(200, json={"id": "job-mag-001", "status": "queued"})
    )
    with patch(_PATCH, return_value=_settings()):
        result = await adapter.generate_image(params)

    assert result.job_id == "job-mag-001"
    assert result.status == "queued"


@pytest.mark.asyncio
@respx.mock
async def test_generate_image_402_raises_budget_exceeded(
    adapter: MagnificAdapter, params: GenerationParams
) -> None:
    respx.post("https://api.magnific.ai/v1/upscaling").mock(
        return_value=Response(402, json={"error": "credits exhausted"})
    )
    with patch(_PATCH, return_value=_settings()), pytest.raises(VosError) as exc:
        await adapter.generate_image(params)
    assert exc.value.error_code == ErrorCode.BUDGET_EXCEEDED


@pytest.mark.asyncio
@respx.mock
async def test_generate_image_401_raises_auth_error(
    adapter: MagnificAdapter, params: GenerationParams
) -> None:
    respx.post("https://api.magnific.ai/v1/upscaling").mock(
        return_value=Response(401, json={"error": "unauthorized"})
    )
    with patch(_PATCH, return_value=_settings()), pytest.raises(VosError) as exc:
        await adapter.generate_image(params)
    assert exc.value.error_code == ErrorCode.PROVIDER_AUTH_ERROR


# ---------------------------------------------------------------------------
# generate_video — must raise
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_video_raises(
    adapter: MagnificAdapter, params: GenerationParams
) -> None:
    with pytest.raises(NotImplementedError):
        await adapter.generate_video(params)


# ---------------------------------------------------------------------------
# check_job_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_check_job_status_queued(adapter: MagnificAdapter) -> None:
    respx.get("https://api.magnific.ai/v1/upscaling/job-mag-001").mock(
        return_value=Response(200, json={"status": "queued"})
    )
    with patch(_PATCH, return_value=_settings()):
        result = await adapter.check_job_status("job-mag-001")

    assert result.job_id == "job-mag-001"
    assert result.status == "queued"
    assert result.error is None


@pytest.mark.asyncio
@respx.mock
async def test_check_job_status_processing(adapter: MagnificAdapter) -> None:
    respx.get("https://api.magnific.ai/v1/upscaling/job-mag-001").mock(
        return_value=Response(200, json={"status": "processing"})
    )
    with patch(_PATCH, return_value=_settings()):
        result = await adapter.check_job_status("job-mag-001")

    assert result.status == "running"


@pytest.mark.asyncio
@respx.mock
async def test_check_job_status_completed(adapter: MagnificAdapter) -> None:
    respx.get("https://api.magnific.ai/v1/upscaling/job-mag-001").mock(
        return_value=Response(
            200,
            json={"status": "completed", "output_url": "https://cdn.magnific.ai/upscaled.jpg"},
        )
    )
    with patch(_PATCH, return_value=_settings()):
        result = await adapter.check_job_status("job-mag-001")

    assert result.status == "completed"
    assert result.media_url == "https://cdn.magnific.ai/upscaled.jpg"


@pytest.mark.asyncio
@respx.mock
async def test_check_job_status_failed(adapter: MagnificAdapter) -> None:
    respx.get("https://api.magnific.ai/v1/upscaling/job-mag-001").mock(
        return_value=Response(200, json={"status": "failed", "error": "image too small"})
    )
    with patch(_PATCH, return_value=_settings()):
        result = await adapter.check_job_status("job-mag-001")

    assert result.status == "failed"
    assert result.error == "image too small"


@pytest.mark.asyncio
@respx.mock
async def test_check_job_status_http_error_raises(adapter: MagnificAdapter) -> None:
    respx.get("https://api.magnific.ai/v1/upscaling/bad-job").mock(
        return_value=Response(404, json={"error": "not found"})
    )
    with patch(_PATCH, return_value=_settings()), pytest.raises(VosError) as exc:
        await adapter.check_job_status("bad-job")
    assert exc.value.error_code == ErrorCode.PROVIDER_ERROR


@pytest.mark.asyncio
async def test_check_job_status_no_api_key_raises(adapter: MagnificAdapter) -> None:
    with patch(_PATCH, return_value=Settings(MAGNIFIC_API_KEY="")), pytest.raises(VosError) as exc:
        await adapter.check_job_status("job-mag-001")
    assert exc.value.error_code == ErrorCode.PROVIDER_ERROR


# ---------------------------------------------------------------------------
# prepare_manual_pack
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prepare_manual_pack_shape(
    adapter: MagnificAdapter, params: GenerationParams
) -> None:
    pack = await adapter.prepare_manual_pack(params)
    assert pack.provider == "magnific"
    assert pack.model == "magnific-upscaler"
    assert len(pack.checklist) > 0
    assert len(pack.qa_criteria) > 0
    assert "spr-mag-001" in pack.naming_convention
    assert "upscaled" in pack.naming_convention


@pytest.mark.asyncio
async def test_prepare_manual_pack_1080p_uses_4x(
    adapter: MagnificAdapter, params: GenerationParams
) -> None:
    params.resolution = "1080p"
    pack = await adapter.prepare_manual_pack(params)
    assert pack.settings["scale"] == 4


# ---------------------------------------------------------------------------
# verify_webhook_signature
# ---------------------------------------------------------------------------


def _make_sig(secret: str, payload: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def test_verify_webhook_valid(adapter: MagnificAdapter) -> None:
    payload = b'{"event":"upscaling.completed"}'
    headers = {"X-Magnific-Signature": _make_sig("mag-secret", payload)}
    with patch(_PATCH, return_value=_settings()):
        assert adapter.verify_webhook_signature(payload, headers) is True


def test_verify_webhook_invalid(adapter: MagnificAdapter) -> None:
    payload = b'{"event":"upscaling.completed"}'
    headers = {"X-Magnific-Signature": "sha256=deadbeef"}
    with patch(_PATCH, return_value=_settings()):
        assert adapter.verify_webhook_signature(payload, headers) is False


def test_verify_webhook_no_secret_rejects(adapter: MagnificAdapter) -> None:
    payload = b'{"event":"test"}'
    headers = {"X-Magnific-Signature": _make_sig("mag-secret", payload)}
    with patch(_PATCH, return_value=Settings(WEBHOOK_SECRET_MAGNIFIC="")):
        assert adapter.verify_webhook_signature(payload, headers) is False


def test_verify_webhook_missing_header_rejects(adapter: MagnificAdapter) -> None:
    with patch(_PATCH, return_value=_settings()):
        assert adapter.verify_webhook_signature(b"data", {}) is False
