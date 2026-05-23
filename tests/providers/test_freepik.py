"""Unit tests for Freepik provider adapter (ADR-0009)."""

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
from vos_studio_mcp.services.providers.freepik import FreepikAdapter

_PATCH = "vos_studio_mcp.services.providers.freepik.get_settings"


def _settings(**kwargs: Any) -> Settings:
    return Settings(FREEPIK_API_KEY="fp-test-key", WEBHOOK_SECRET_FREEPIK="fp-secret", **kwargs)


@pytest.fixture
def adapter() -> FreepikAdapter:
    return FreepikAdapter()


@pytest.fixture
def params() -> GenerationParams:
    return GenerationParams(
        sprint_id="spr-fp-001",
        prompt_version="v1",
        preset_version="p1",
        mode="api_credits",
        approval_token="tok-approved",
        prompt="A bright skincare product on white background",
        resolution="720p",
        duration_seconds=5,
        aspect_ratio="16:9",
    )


# ---------------------------------------------------------------------------
# estimate_cost
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_estimate_cost_returns_fixed_price(
    adapter: FreepikAdapter, params: GenerationParams
) -> None:
    result = await adapter.estimate_cost(params)
    assert result.estimated_usd == 0.01
    assert result.uncertain is False


# ---------------------------------------------------------------------------
# generate_image
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_image_no_api_key_raises(
    adapter: FreepikAdapter, params: GenerationParams
) -> None:
    with patch(_PATCH, return_value=Settings(FREEPIK_API_KEY="")), pytest.raises(VosError) as exc:
        await adapter.generate_image(params)
    assert exc.value.error_code == ErrorCode.PROVIDER_ERROR


@pytest.mark.asyncio
async def test_generate_image_no_approval_token_raises(
    adapter: FreepikAdapter, params: GenerationParams
) -> None:
    params.approval_token = None
    with patch(_PATCH, return_value=_settings()), pytest.raises(VosError) as exc:
        await adapter.generate_image(params)
    assert exc.value.error_code == ErrorCode.INVALID_INPUT


@pytest.mark.asyncio
@respx.mock
async def test_generate_image_success(
    adapter: FreepikAdapter, params: GenerationParams
) -> None:
    respx.post("https://api.freepik.com/v1/ai/text-to-image").mock(
        return_value=Response(200, json={"data": {"task_id": "task-fp-123"}})
    )
    with patch(_PATCH, return_value=_settings()):
        result = await adapter.generate_image(params)

    assert result.job_id == "task-fp-123"
    assert result.status == "queued"


@pytest.mark.asyncio
@respx.mock
async def test_generate_image_402_raises_budget_exceeded(
    adapter: FreepikAdapter, params: GenerationParams
) -> None:
    respx.post("https://api.freepik.com/v1/ai/text-to-image").mock(
        return_value=Response(402, json={"error": "credits exhausted"})
    )
    with patch(_PATCH, return_value=_settings()), pytest.raises(VosError) as exc:
        await adapter.generate_image(params)
    assert exc.value.error_code == ErrorCode.BUDGET_EXCEEDED


@pytest.mark.asyncio
@respx.mock
async def test_generate_image_401_raises_provider_auth_error(
    adapter: FreepikAdapter, params: GenerationParams
) -> None:
    respx.post("https://api.freepik.com/v1/ai/text-to-image").mock(
        return_value=Response(401, json={"error": "invalid api key"})
    )
    with patch(_PATCH, return_value=_settings()), pytest.raises(VosError) as exc:
        await adapter.generate_image(params)
    assert exc.value.error_code == ErrorCode.PROVIDER_AUTH_ERROR


@pytest.mark.asyncio
@respx.mock
async def test_generate_image_500_raises_provider_error(
    adapter: FreepikAdapter, params: GenerationParams
) -> None:
    respx.post("https://api.freepik.com/v1/ai/text-to-image").mock(
        return_value=Response(500, json={"error": "internal error"})
    )
    with patch(_PATCH, return_value=_settings()), pytest.raises(VosError) as exc:
        await adapter.generate_image(params)
    assert exc.value.error_code == ErrorCode.PROVIDER_ERROR


# ---------------------------------------------------------------------------
# generate_video — must raise
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_video_raises(
    adapter: FreepikAdapter, params: GenerationParams
) -> None:
    with pytest.raises(NotImplementedError):
        await adapter.generate_video(params)


# ---------------------------------------------------------------------------
# check_job_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_check_job_status_pending(adapter: FreepikAdapter) -> None:
    respx.get("https://api.freepik.com/v1/ai/text-to-image/task-fp-123").mock(
        return_value=Response(200, json={"data": {"status": "PENDING"}})
    )
    with patch(_PATCH, return_value=_settings()):
        result = await adapter.check_job_status("task-fp-123")

    assert result.job_id == "task-fp-123"
    assert result.status == "queued"
    assert result.error is None


@pytest.mark.asyncio
@respx.mock
async def test_check_job_status_completed(adapter: FreepikAdapter) -> None:
    respx.get("https://api.freepik.com/v1/ai/text-to-image/task-fp-123").mock(
        return_value=Response(
            200,
            json={
                "data": {
                    "status": "COMPLETED",
                    "generated": [{"url": "https://cdn.freepik.com/img.jpg"}],
                }
            },
        )
    )
    with patch(_PATCH, return_value=_settings()):
        result = await adapter.check_job_status("task-fp-123")

    assert result.status == "completed"
    assert result.media_url == "https://cdn.freepik.com/img.jpg"


@pytest.mark.asyncio
@respx.mock
async def test_check_job_status_failed(adapter: FreepikAdapter) -> None:
    respx.get("https://api.freepik.com/v1/ai/text-to-image/task-fp-123").mock(
        return_value=Response(
            200, json={"data": {"status": "FAILED", "error": "content policy"}}
        )
    )
    with patch(_PATCH, return_value=_settings()):
        result = await adapter.check_job_status("task-fp-123")

    assert result.status == "failed"
    assert result.error == "content policy"


@pytest.mark.asyncio
@respx.mock
async def test_check_job_status_http_error_raises(adapter: FreepikAdapter) -> None:
    respx.get("https://api.freepik.com/v1/ai/text-to-image/bad-task").mock(
        return_value=Response(404, json={"error": "not found"})
    )
    with patch(_PATCH, return_value=_settings()), pytest.raises(VosError) as exc:
        await adapter.check_job_status("bad-task")
    assert exc.value.error_code == ErrorCode.PROVIDER_ERROR


# ---------------------------------------------------------------------------
# prepare_manual_pack
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prepare_manual_pack_shape(
    adapter: FreepikAdapter, params: GenerationParams
) -> None:
    pack = await adapter.prepare_manual_pack(params)
    assert pack.provider == "freepik"
    assert pack.model == "mystic"
    assert len(pack.checklist) > 0
    assert len(pack.qa_criteria) > 0
    assert "spr-fp-001" in pack.naming_convention
    assert pack.prompt == "A bright skincare product on white background"


# ---------------------------------------------------------------------------
# verify_webhook_signature
# ---------------------------------------------------------------------------


def _make_sig(secret: str, payload: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def test_verify_webhook_valid(adapter: FreepikAdapter) -> None:
    payload = b'{"event":"generation.completed"}'
    headers = {"X-Freepik-Signature": _make_sig("fp-secret", payload)}
    with patch(_PATCH, return_value=_settings()):
        assert adapter.verify_webhook_signature(payload, headers) is True


def test_verify_webhook_invalid(adapter: FreepikAdapter) -> None:
    payload = b'{"event":"generation.completed"}'
    headers = {"X-Freepik-Signature": "sha256=deadbeef"}
    with patch(_PATCH, return_value=_settings()):
        assert adapter.verify_webhook_signature(payload, headers) is False


def test_verify_webhook_no_secret_rejects(adapter: FreepikAdapter) -> None:
    payload = b'{"event":"test"}'
    headers = {"X-Freepik-Signature": _make_sig("fp-secret", payload)}
    with patch(_PATCH, return_value=Settings(WEBHOOK_SECRET_FREEPIK="")):
        assert adapter.verify_webhook_signature(payload, headers) is False


def test_verify_webhook_missing_header_rejects(adapter: FreepikAdapter) -> None:
    with patch(_PATCH, return_value=_settings()):
        assert adapter.verify_webhook_signature(b"data", {}) is False


def test_verify_webhook_lowercase_header(adapter: FreepikAdapter) -> None:
    payload = b'{"event":"test"}'
    headers = {"x-freepik-signature": _make_sig("fp-secret", payload)}
    with patch(_PATCH, return_value=_settings()):
        assert adapter.verify_webhook_signature(payload, headers) is True


@pytest.mark.asyncio
async def test_check_job_status_no_api_key_raises(adapter: FreepikAdapter) -> None:
    """check_job_status should raise PROVIDER_ERROR when FREEPIK_API_KEY is unset."""
    from vos_studio_mcp.config.env import Settings

    with patch(_PATCH, return_value=Settings(FREEPIK_API_KEY="")), pytest.raises(VosError) as exc:
        await adapter.check_job_status("task-fp-001")
    assert exc.value.error_code == ErrorCode.PROVIDER_ERROR
