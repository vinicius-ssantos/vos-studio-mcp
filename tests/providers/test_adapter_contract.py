"""Adapter contract tests — every ProviderAdapter implementation must pass (ADR-0026 Layer 3).

Tests are parametrized over all registered adapters and verify that each satisfies
the ProviderAdapter Protocol contract without calling real provider APIs.
"""

from typing import Any
from unittest.mock import patch

import pytest

from vos_studio_mcp.services.providers.base import (
    CostEstimate,
    GenerationParams,
    JobStatus,
    ManualPack,
    ProviderAdapter,
)
from vos_studio_mcp.services.providers.higgsfield import HiggsFieldAdapter
from vos_studio_mcp.services.providers.manual_dashboard import ManualDashboardAdapter

# ---------------------------------------------------------------------------
# Adapter fixtures
# ---------------------------------------------------------------------------

_HIGGSFIELD_SETTINGS_PATCH = "vos_studio_mcp.services.providers.higgsfield.get_settings"


def _higgsfield_settings() -> Any:
    from vos_studio_mcp.config.env import Settings

    return Settings(HIGGSFIELD_API_KEY="test-key", WEBHOOK_SECRET_HIGGSFIELD="wh-secret")


def _base_params(mode: str = "dashboard_manual") -> GenerationParams:
    return GenerationParams(
        sprint_id="spr-contract-test",
        prompt_version="v1",
        preset_version="p1",
        mode=mode,  # type: ignore[arg-type]
        prompt="A cinematic product launch video",
        resolution="720p",
        duration_seconds=5,
        aspect_ratio="16:9",
    )


# ---------------------------------------------------------------------------
# Protocol structural check
# ---------------------------------------------------------------------------


def test_higgsfield_adapter_satisfies_protocol() -> None:
    """HiggsFieldAdapter must be a runtime-checkable ProviderAdapter."""
    assert isinstance(HiggsFieldAdapter(), ProviderAdapter)


def test_manual_dashboard_adapter_satisfies_protocol() -> None:
    """ManualDashboardAdapter must be a runtime-checkable ProviderAdapter."""
    assert isinstance(ManualDashboardAdapter(), ProviderAdapter)


# ---------------------------------------------------------------------------
# estimate_cost — must never call the provider API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_estimate_cost_returns_cost_estimate_higgsfield() -> None:
    with patch(_HIGGSFIELD_SETTINGS_PATCH, return_value=_higgsfield_settings()):
        result = await HiggsFieldAdapter().estimate_cost(_base_params("api_credits"))
    assert isinstance(result, CostEstimate)
    assert result.estimated_usd >= 0


@pytest.mark.asyncio
async def test_estimate_cost_returns_cost_estimate_manual() -> None:
    result = await ManualDashboardAdapter().estimate_cost(_base_params())
    assert isinstance(result, CostEstimate)
    assert result.estimated_usd == 0.0
    assert result.uncertain is False


# ---------------------------------------------------------------------------
# generate_image — must raise NotImplementedError on both adapters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_image_raises_not_implemented_higgsfield() -> None:
    with pytest.raises(NotImplementedError):
        await HiggsFieldAdapter().generate_image(_base_params("api_credits"))


@pytest.mark.asyncio
async def test_generate_image_raises_not_implemented_manual() -> None:
    with pytest.raises(NotImplementedError):
        await ManualDashboardAdapter().generate_image(_base_params())


# ---------------------------------------------------------------------------
# generate_video — manual adapter must raise, higgsfield requires API key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_video_raises_not_implemented_manual() -> None:
    with pytest.raises(NotImplementedError):
        await ManualDashboardAdapter().generate_video(_base_params())


# ---------------------------------------------------------------------------
# check_job_status — manual adapter returns a valid JobStatus (no-op)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_job_status_returns_valid_job_status_manual() -> None:
    result = await ManualDashboardAdapter().check_job_status("job-123")
    assert isinstance(result, JobStatus)
    assert result.job_id == "job-123"


# ---------------------------------------------------------------------------
# prepare_manual_pack — must return a ManualPack with required fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prepare_manual_pack_shape_higgsfield() -> None:
    pack = await HiggsFieldAdapter().prepare_manual_pack(_base_params())
    _assert_manual_pack(pack, "higgsfield")


@pytest.mark.asyncio
async def test_prepare_manual_pack_shape_manual() -> None:
    pack = await ManualDashboardAdapter().prepare_manual_pack(_base_params())
    _assert_manual_pack(pack, "manual_dashboard")


def _assert_manual_pack(pack: ManualPack, provider: str) -> None:
    assert pack.provider == provider
    assert isinstance(pack.checklist, list)
    assert len(pack.checklist) > 0
    assert isinstance(pack.qa_criteria, list)
    assert len(pack.qa_criteria) > 0
    assert isinstance(pack.naming_convention, str)
    assert len(pack.naming_convention) > 0


# ---------------------------------------------------------------------------
# verify_webhook_signature — fail-safe contract
# ---------------------------------------------------------------------------


def test_verify_webhook_no_secret_returns_false_higgsfield() -> None:
    """Missing secret must return False, never raise."""
    from vos_studio_mcp.config.env import Settings

    with patch(_HIGGSFIELD_SETTINGS_PATCH, return_value=Settings(WEBHOOK_SECRET_HIGGSFIELD="")):
        result = HiggsFieldAdapter().verify_webhook_signature(b"payload", {})
    assert result is False


def test_verify_webhook_always_true_manual() -> None:
    """ManualDashboardAdapter has no webhook secrets — must always accept."""
    assert ManualDashboardAdapter().verify_webhook_signature(b"any", {}) is True


def test_verify_webhook_never_raises_on_bad_headers_higgsfield() -> None:
    """Malformed headers must not raise — just return False."""
    with patch(_HIGGSFIELD_SETTINGS_PATCH, return_value=_higgsfield_settings()):
        result = HiggsFieldAdapter().verify_webhook_signature(b"payload", {"X-Bad": "garbage"})
    assert result is False
