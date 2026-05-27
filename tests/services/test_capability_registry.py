"""Unit tests for the provider capability registry (Issue #44)."""

import pytest

from vos_studio_mcp.services.providers.capability_registry import (
    get_capability,
    get_providers_for_capability,
    list_capabilities,
)

# ---------------------------------------------------------------------------
# list_capabilities — enabled_only=True (default)
# ---------------------------------------------------------------------------


def test_list_capabilities_enabled_only_returns_four() -> None:
    """Four providers are default-enabled; cloudflare_workers_ai is not."""
    caps = list_capabilities(enabled_only=True)
    assert len(caps) == 4


def test_list_capabilities_enabled_only_excludes_cloudflare() -> None:
    ids = {c.provider_id for c in list_capabilities(enabled_only=True)}
    assert "cloudflare_workers_ai" not in ids


def test_list_capabilities_all_includes_cloudflare() -> None:
    ids = {c.provider_id for c in list_capabilities(enabled_only=False)}
    assert "cloudflare_workers_ai" in ids


def test_list_capabilities_all_returns_five() -> None:
    caps = list_capabilities(enabled_only=False)
    assert len(caps) == 5


# ---------------------------------------------------------------------------
# get_capability — happy path
# ---------------------------------------------------------------------------


def test_get_capability_higgsfield_fields() -> None:
    cap = get_capability("higgsfield")
    assert cap.provider_id == "higgsfield"
    assert cap.display_name == "Higgsfield Animate"
    assert "image_to_video" in cap.capabilities
    assert cap.supports_webhooks is True
    assert cap.supports_polling is True
    assert cap.requires_api_key is True
    assert cap.has_free_tier is False
    assert cap.paid_side_effect_risk is True
    assert cap.requires_human_approval_for_execution is True
    assert cap.default_enabled is True


def test_get_capability_unknown_raises_key_error() -> None:
    with pytest.raises(KeyError, match="unknown_provider"):
        get_capability("unknown_provider")


# ---------------------------------------------------------------------------
# Required fields — all enabled providers
# ---------------------------------------------------------------------------


def test_all_enabled_providers_have_required_fields() -> None:
    required_str_fields = ["provider_id", "display_name", "notes"]
    required_list_fields = ["modes", "capabilities"]
    for cap in list_capabilities(enabled_only=True):
        for f in required_str_fields:
            assert isinstance(getattr(cap, f), str), f"{cap.provider_id}.{f} must be str"
        for f in required_list_fields:
            val = getattr(cap, f)
            assert isinstance(val, list) and len(val) > 0, f"{cap.provider_id}.{f} must be non-empty list"


# ---------------------------------------------------------------------------
# Safety invariants
# ---------------------------------------------------------------------------


def test_all_paid_providers_require_human_approval() -> None:
    """Every provider with paid_side_effect_risk=True must require human approval."""
    for cap in list_capabilities(enabled_only=False):
        if cap.paid_side_effect_risk:
            assert cap.requires_human_approval_for_execution is True, (
                f"{cap.provider_id}: paid_side_effect_risk=True but requires_human_approval=False"
            )


def test_manual_dashboard_has_no_paid_side_effect_risk() -> None:
    cap = get_capability("manual_dashboard")
    assert cap.paid_side_effect_risk is False


def test_cloudflare_workers_ai_is_disabled_by_default() -> None:
    cap = get_capability("cloudflare_workers_ai")
    assert cap.default_enabled is False


# ---------------------------------------------------------------------------
# get_providers_for_capability
# ---------------------------------------------------------------------------


def test_get_providers_for_text_to_image_returns_correct_providers() -> None:
    caps = get_providers_for_capability("text_to_image")
    ids = {c.provider_id for c in caps}
    # manual_dashboard and freepik support text_to_image and are default-enabled
    assert "manual_dashboard" in ids
    assert "freepik" in ids
    # higgsfield only supports image_to_video
    assert "higgsfield" not in ids


def test_get_providers_for_text_to_image_excludes_disabled_by_default() -> None:
    """cloudflare_workers_ai supports text_to_image but is disabled by default."""
    enabled_caps = get_providers_for_capability("text_to_image", enabled_only=True)
    enabled_ids = {c.provider_id for c in enabled_caps}
    assert "cloudflare_workers_ai" not in enabled_ids


def test_get_providers_for_text_to_image_includes_disabled_when_requested() -> None:
    all_caps = get_providers_for_capability("text_to_image", enabled_only=False)
    all_ids = {c.provider_id for c in all_caps}
    assert "cloudflare_workers_ai" in all_ids


def test_get_providers_for_upscale_returns_magnific() -> None:
    caps = get_providers_for_capability("upscale")
    ids = {c.provider_id for c in caps}
    assert "magnific" in ids
