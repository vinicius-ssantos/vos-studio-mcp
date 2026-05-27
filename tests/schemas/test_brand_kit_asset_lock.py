"""Schema tests for BrandKit asset_lock (Issue #56)."""


from vos_studio_mcp.schemas.brand_kit import (
    AssetLock,
    BrandIdentity,
    BrandKitInput,
    BrandRestrictions,
    BrandVisualSystem,
)

# ---------------------------------------------------------------------------
# Minimal helpers
# ---------------------------------------------------------------------------


def _make_brand_kit_input(**kwargs) -> BrandKitInput:  # type: ignore[return]
    return BrandKitInput(
        client_id="aaaaaaaa-0000-0000-0000-aaaaaaaaaaaa",
        name="Test Brand",
        identity=BrandIdentity(
            brand_name="TestCo",
            target_audience="Gen-Z",
            positioning="Bold and authentic",
        ),
        visual=BrandVisualSystem(),
        restrictions=BrandRestrictions(),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# AssetLock defaults
# ---------------------------------------------------------------------------


def test_asset_lock_all_fields_optional() -> None:
    lock = AssetLock()
    assert lock.dominant_register == ""
    assert lock.secondary_register == ""
    assert lock.forbidden_register == []
    assert lock.allowed_materials == []
    assert lock.forbidden_materials == []
    assert lock.allowed_environments == []
    assert lock.forbidden_environments == []
    assert lock.text_policy == ""
    assert lock.endcard_policy == ""
    assert lock.reference_asset_ids == []


def test_asset_lock_accepts_all_fields() -> None:
    lock = AssetLock(
        dominant_register="bold product-forward",
        secondary_register="warm lifestyle",
        forbidden_register=["dark/gothic", "cold clinical"],
        allowed_materials=["glass", "natural wood"],
        forbidden_materials=["plastic", "neon"],
        allowed_environments=["kitchen", "outdoor park"],
        forbidden_environments=["office", "hospital"],
        text_policy="no text except CTA on shot 8",
        endcard_policy="brand logo + CTA button, 2s minimum",
        reference_asset_ids=["aa-bb-cc", "dd-ee-ff"],
    )
    assert lock.dominant_register == "bold product-forward"
    assert "glass" in lock.allowed_materials
    assert len(lock.reference_asset_ids) == 2


# ---------------------------------------------------------------------------
# BrandKitInput with asset_lock
# ---------------------------------------------------------------------------


def test_brand_kit_input_asset_lock_defaults_to_none() -> None:
    data = _make_brand_kit_input()
    assert data.asset_lock is None


def test_brand_kit_input_accepts_asset_lock() -> None:
    lock = AssetLock(
        dominant_register="bold product-forward",
        forbidden_environments=["hospital", "office"],
        text_policy="no text except CTA",
    )
    data = _make_brand_kit_input(asset_lock=lock)
    assert data.asset_lock is not None
    assert data.asset_lock.dominant_register == "bold product-forward"
    assert "hospital" in data.asset_lock.forbidden_environments
    assert data.asset_lock.text_policy == "no text except CTA"


def test_brand_kit_input_asset_lock_model_dump() -> None:
    lock = AssetLock(
        allowed_materials=["glass"],
        forbidden_materials=["plastic"],
    )
    data = _make_brand_kit_input(asset_lock=lock)
    dumped = data.asset_lock.model_dump()  # type: ignore[union-attr]
    assert dumped["allowed_materials"] == ["glass"]
    assert dumped["forbidden_materials"] == ["plastic"]


# ---------------------------------------------------------------------------
# Blueprint negative prompts with asset_lock
# ---------------------------------------------------------------------------


def test_blueprint_negative_prompts_include_asset_lock_forbidden() -> None:
    from vos_studio_mcp.services.blueprint_service import _build_negative_prompts

    restrictions = {"forbidden_elements": ["alcohol"]}
    asset_lock = {
        "forbidden_register": ["dark/gothic"],
        "forbidden_materials": ["neon plastic"],
        "forbidden_environments": ["hospital"],
    }
    result = _build_negative_prompts(restrictions, asset_lock)
    assert "alcohol" in result
    assert "dark/gothic" in result
    assert "neon plastic" in result
    assert "hospital" in result


def test_blueprint_negative_prompts_without_asset_lock() -> None:
    from vos_studio_mcp.services.blueprint_service import _build_negative_prompts

    restrictions = {"forbidden_elements": ["alcohol"]}
    result = _build_negative_prompts(restrictions)
    assert "alcohol" in result
    assert len(result) >= 6  # base 5 + forbidden_elements


def test_blueprint_negative_prompts_empty_asset_lock() -> None:
    from vos_studio_mcp.services.blueprint_service import _build_negative_prompts

    result = _build_negative_prompts({}, {})
    assert len(result) == 5  # base only
