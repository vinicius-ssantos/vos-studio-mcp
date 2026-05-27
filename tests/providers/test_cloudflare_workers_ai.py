"""Unit tests for Cloudflare Workers AI provider adapter (Issue #43)."""

from base64 import b64encode
from typing import Any
from unittest.mock import patch

import pytest
import respx
from httpx import Response, TimeoutException

from vos_studio_mcp.config.env import Settings
from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.services.providers.base import GenerationParams
from vos_studio_mcp.services.providers.cloudflare_workers_ai import (
    CloudflareWorkersAIAdapter,
    get_cloudflare_adapter,
)

_PATCH = "vos_studio_mcp.services.providers.cloudflare_workers_ai.get_settings"

_CF_URL = (
    "https://api.cloudflare.com/client/v4/accounts/acct-123/ai/run"
    "/@cf/black-forest-labs/flux-1-schnell"
)


def _settings(**kwargs: Any) -> Settings:
    return Settings(
        CLOUDFLARE_WORKERS_AI_ENABLED=True,
        CLOUDFLARE_ACCOUNT_ID="acct-123",
        CLOUDFLARE_API_TOKEN="tok-abc",
        **kwargs,
    )


@pytest.fixture
def adapter() -> CloudflareWorkersAIAdapter:
    return CloudflareWorkersAIAdapter(account_id="acct-123", api_token="tok-abc")


@pytest.fixture
def params() -> GenerationParams:
    return GenerationParams(
        sprint_id="spr-cf-001",
        prompt_version="v1",
        preset_version="p1",
        mode="api_free_public",
        prompt="A futuristic city skyline at night",
        resolution="720p",
        duration_seconds=5,
        aspect_ratio="16:9",
    )


# ---------------------------------------------------------------------------
# get_cloudflare_adapter — factory guard checks
# ---------------------------------------------------------------------------


def test_get_cloudflare_adapter_disabled_raises() -> None:
    with patch(_PATCH, return_value=Settings(CLOUDFLARE_WORKERS_AI_ENABLED=False)), pytest.raises(VosError) as exc:
        get_cloudflare_adapter()
    assert exc.value.error_code == ErrorCode.PROVIDER_UNAVAILABLE


def test_get_cloudflare_adapter_missing_credentials_raises() -> None:
    with patch(
        _PATCH,
        return_value=Settings(
            CLOUDFLARE_WORKERS_AI_ENABLED=True,
            CLOUDFLARE_ACCOUNT_ID="",
            CLOUDFLARE_API_TOKEN="",
        ),
    ), pytest.raises(VosError) as exc:
        get_cloudflare_adapter()
    assert exc.value.error_code == ErrorCode.PROVIDER_UNAVAILABLE


def test_get_cloudflare_adapter_returns_adapter() -> None:
    with patch(_PATCH, return_value=_settings()):
        result = get_cloudflare_adapter()
    assert isinstance(result, CloudflareWorkersAIAdapter)
    assert result.provider_id == "cloudflare_workers_ai"


# ---------------------------------------------------------------------------
# estimate_cost
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_estimate_cost_returns_zero(
    adapter: CloudflareWorkersAIAdapter, params: GenerationParams
) -> None:
    result = await adapter.estimate_cost(params)
    assert result.estimated_usd == 0.0
    assert result.uncertain is False


# ---------------------------------------------------------------------------
# generate_video — not supported
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_video_raises_provider_error(
    adapter: CloudflareWorkersAIAdapter, params: GenerationParams
) -> None:
    with pytest.raises(VosError) as exc:
        await adapter.generate_video(params)
    assert exc.value.error_code == ErrorCode.PROVIDER_ERROR


# ---------------------------------------------------------------------------
# check_job_status — not supported
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_job_status_raises_provider_error(
    adapter: CloudflareWorkersAIAdapter,
) -> None:
    with pytest.raises(VosError) as exc:
        await adapter.check_job_status("some-job-id")
    assert exc.value.error_code == ErrorCode.PROVIDER_ERROR


# ---------------------------------------------------------------------------
# generate_image
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_image_disabled_raises(
    adapter: CloudflareWorkersAIAdapter, params: GenerationParams
) -> None:
    with patch(
        _PATCH,
        return_value=Settings(CLOUDFLARE_WORKERS_AI_ENABLED=False),
    ), pytest.raises(VosError) as exc:
        await adapter.generate_image(params)
    assert exc.value.error_code == ErrorCode.PROVIDER_UNAVAILABLE


@pytest.mark.asyncio
@respx.mock
async def test_generate_image_success(
    adapter: CloudflareWorkersAIAdapter, params: GenerationParams
) -> None:
    image_bytes = b"fake-image-data"
    encoded = b64encode(image_bytes).decode()
    respx.post(_CF_URL).mock(
        return_value=Response(
            200, json={"success": True, "result": {"image": encoded}, "errors": []}
        )
    )
    with patch(_PATCH, return_value=_settings()):
        result = await adapter.generate_image(params)

    assert result.status == "completed"
    assert result.job_id  # synthetic uuid


@pytest.mark.asyncio
@respx.mock
async def test_generate_image_timeout_raises(
    adapter: CloudflareWorkersAIAdapter, params: GenerationParams
) -> None:
    respx.post(_CF_URL).mock(side_effect=TimeoutException("timed out"))
    with patch(_PATCH, return_value=_settings()), pytest.raises(VosError) as exc:
        await adapter.generate_image(params)
    assert exc.value.error_code == ErrorCode.PROVIDER_TIMEOUT


@pytest.mark.asyncio
@respx.mock
async def test_generate_image_non_200_raises(
    adapter: CloudflareWorkersAIAdapter, params: GenerationParams
) -> None:
    respx.post(_CF_URL).mock(
        return_value=Response(500, json={"errors": ["internal server error"]})
    )
    with patch(_PATCH, return_value=_settings()), pytest.raises(VosError) as exc:
        await adapter.generate_image(params)
    assert exc.value.error_code == ErrorCode.PROVIDER_ERROR


@pytest.mark.asyncio
@respx.mock
async def test_generate_image_api_success_false_raises(
    adapter: CloudflareWorkersAIAdapter, params: GenerationParams
) -> None:
    respx.post(_CF_URL).mock(
        return_value=Response(
            200, json={"success": False, "errors": [{"code": 1001, "message": "bad request"}]}
        )
    )
    with patch(_PATCH, return_value=_settings()), pytest.raises(VosError) as exc:
        await adapter.generate_image(params)
    assert exc.value.error_code == ErrorCode.PROVIDER_ERROR


# ---------------------------------------------------------------------------
# verify_webhook_signature — always False
# ---------------------------------------------------------------------------


def test_verify_webhook_signature_always_false(
    adapter: CloudflareWorkersAIAdapter,
) -> None:
    result = adapter.verify_webhook_signature(b'{"event": "test"}', {"X-Sig": "abc"})
    assert result is False


def test_verify_webhook_signature_empty_returns_false(
    adapter: CloudflareWorkersAIAdapter,
) -> None:
    assert adapter.verify_webhook_signature(b"", {}) is False


# ---------------------------------------------------------------------------
# prepare_manual_pack
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prepare_manual_pack_shape(
    adapter: CloudflareWorkersAIAdapter, params: GenerationParams
) -> None:
    pack = await adapter.prepare_manual_pack(params)
    assert pack.provider == "cloudflare_workers_ai"
    assert "spr-cf-001" in pack.naming_convention
    assert len(pack.checklist) > 0
    assert len(pack.qa_criteria) > 0
