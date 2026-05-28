"""Schema tests for asset stage / kind / lineage fields (Issue #53)."""

import pytest
from pydantic import ValidationError

from vos_studio_mcp.schemas.asset import (
    _ASSET_STAGE_LABELS,
    AssetInput,
    AssetListItem,
)

# ---------------------------------------------------------------------------
# _ASSET_STAGE_LABELS coverage
# ---------------------------------------------------------------------------


def test_stage_labels_cover_all_stage_values() -> None:
    stages: tuple[str, ...] = ("stage_0", "stage_a", "stage_b", "stage_c", "repair", "final")
    for stage in stages:
        assert stage in _ASSET_STAGE_LABELS
        assert _ASSET_STAGE_LABELS[stage]  # non-empty label


# ---------------------------------------------------------------------------
# AssetInput defaults
# ---------------------------------------------------------------------------


def test_asset_input_stage_defaults_to_none() -> None:
    data = AssetInput(
        sprint_id="s",
        provider="manual",
        storage_url="https://example.com/a.mp4",
    )
    assert data.prompt_version == "v1"
    assert data.preset_version == "p1"
    assert data.asset_stage is None
    assert data.asset_kind == "manual"
    assert data.source_asset_id is None
    assert data.approved_as_reference is False
    assert data.is_final_delivery is False


def test_asset_input_accepts_all_stages() -> None:
    for stage in ("stage_0", "stage_a", "stage_b", "stage_c", "repair", "final"):
        data = AssetInput(
            sprint_id="s",
            provider="manual",
            prompt_version="v1",
            preset_version="p1",
            storage_url="https://example.com/a.mp4",
            asset_stage=stage,  # type: ignore[arg-type]
        )
        assert data.asset_stage == stage


def test_asset_input_accepts_agent_friendly_aliases() -> None:
    data = AssetInput(
        sprint_id="s",
        provider="manual",
        uri="https://example.com/a.png",
        mime_type="image/png",
    )
    assert data.storage_url == "https://example.com/a.png"
    assert data.format == "image/png"


def test_asset_input_accepts_all_kinds() -> None:
    for kind in ("generated", "manual", "upscaled"):
        data = AssetInput(
            sprint_id="s",
            provider="manual",
            prompt_version="v1",
            preset_version="p1",
            storage_url="https://example.com/a.mp4",
            asset_kind=kind,  # type: ignore[arg-type]
        )
        assert data.asset_kind == kind


def test_asset_input_invalid_stage_raises() -> None:
    with pytest.raises(ValidationError):
        AssetInput(
            sprint_id="s",
            provider="manual",
            prompt_version="v1",
            preset_version="p1",
            storage_url="https://example.com/a.mp4",
            asset_stage="stage_x",  # type: ignore[arg-type]
        )


def test_asset_input_invalid_kind_raises() -> None:
    with pytest.raises(ValidationError):
        AssetInput(
            sprint_id="s",
            provider="manual",
            prompt_version="v1",
            preset_version="p1",
            storage_url="https://example.com/a.mp4",
            asset_kind="raw",  # type: ignore[arg-type]
        )


def test_asset_input_source_asset_id_optional() -> None:
    data = AssetInput(
        sprint_id="s",
        provider="manual",
        prompt_version="v1",
        preset_version="p1",
        storage_url="https://example.com/a.mp4",
        source_asset_id="aaaaaaaa-0000-0000-0000-aaaaaaaaaaaa",
    )
    assert data.source_asset_id == "aaaaaaaa-0000-0000-0000-aaaaaaaaaaaa"


def test_asset_input_approved_as_reference_true() -> None:
    data = AssetInput(
        sprint_id="s",
        provider="manual",
        prompt_version="v1",
        preset_version="p1",
        storage_url="https://example.com/a.mp4",
        approved_as_reference=True,
    )
    assert data.approved_as_reference is True


def test_asset_input_is_final_delivery_true() -> None:
    data = AssetInput(
        sprint_id="s",
        provider="manual",
        prompt_version="v1",
        preset_version="p1",
        storage_url="https://example.com/a.mp4",
        is_final_delivery=True,
    )
    assert data.is_final_delivery is True


# ---------------------------------------------------------------------------
# AssetListItem stage fields
# ---------------------------------------------------------------------------


def test_asset_list_item_stage_fields_present() -> None:
    item = AssetListItem(
        asset_id="a1",
        provider="manual",
        prompt_version="v1",
        preset_version="p1",
        storage_url="https://example.com/a.mp4",
        asset_stage="stage_c",
        asset_stage_label="Stage C â€” Video",
        asset_kind="generated",
        source_asset_id=None,
        approved_as_reference=False,
        is_final_delivery=True,
        generation_status="completed",
        storage_status="stored",
    )
    assert item.asset_stage == "stage_c"
    assert item.asset_stage_label == "Stage C â€” Video"
    assert item.asset_kind == "generated"
    assert item.is_final_delivery is True
    assert item.generation_status == "completed"
    assert item.storage_status == "stored"


def test_asset_list_item_stage_defaults_to_none() -> None:
    item = AssetListItem(
        asset_id="a1",
        provider="manual",
        prompt_version="v1",
        preset_version="p1",
        storage_url="https://example.com/a.mp4",
    )
    assert item.asset_stage is None
    assert item.asset_stage_label is None
    assert item.asset_kind == "manual"
    assert item.approved_as_reference is False
    assert item.is_final_delivery is False
