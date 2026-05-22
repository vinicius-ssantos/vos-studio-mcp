import pytest
from src.vos_studio_mcp.services.providers.manual_dashboard import ManualDashboardAdapter
from src.vos_studio_mcp.services.providers.base import GenerationParams


@pytest.fixture
def adapter() -> ManualDashboardAdapter:
    return ManualDashboardAdapter()


@pytest.fixture
def params() -> GenerationParams:
    return GenerationParams(
        sprint_id="spr_test",
        prompt_version="v1",
        preset_version="v1",
        mode="dashboard_manual",
    )


@pytest.mark.asyncio
async def test_estimate_cost_is_zero(adapter, params) -> None:
    result = await adapter.estimate_cost(params)
    assert result.estimated_usd == 0.0
    assert result.uncertain is False


@pytest.mark.asyncio
async def test_generate_image_raises(adapter, params) -> None:
    with pytest.raises(NotImplementedError):
        await adapter.generate_image(params)


@pytest.mark.asyncio
async def test_generate_video_raises(adapter, params) -> None:
    with pytest.raises(NotImplementedError):
        await adapter.generate_video(params)


@pytest.mark.asyncio
async def test_prepare_manual_pack_returns_pack(adapter, params) -> None:
    pack = await adapter.prepare_manual_pack(params)
    assert pack.provider == "manual_dashboard"
    assert len(pack.checklist) > 0
    assert len(pack.qa_criteria) > 0


def test_verify_webhook_signature_always_true(adapter) -> None:
    assert adapter.verify_webhook_signature(b"payload", {}) is True
