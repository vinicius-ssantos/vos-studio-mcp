"""Unit tests for the provider capability registry (capabilities.py)."""

import pytest

from vos_studio_mcp.services.providers.capabilities import (
    get_all_provider_ids,
    get_provider_capability,
    list_provider_capabilities,
)

# ---------------------------------------------------------------------------
# list_provider_capabilities — enabled_only (default)
# ---------------------------------------------------------------------------


def test_list_capabilities_enabled_only_returns_four() -> None:
    """Four providers are default-enabled; cloudflare_workers_ai is disabled."""
    caps = list_provider_capabilities(include_disabled=False)
    assert len(caps) == 4


def test_list_capabilities_enabled_only_excludes_cloudflare() -> None:
    ids = {c.provider_id for c in list_provider_capabilities(include_disabled=False)}
    assert "cloudflare_workers_ai" not in ids


def test_list_capabilities_all_includes_cloudflare() -> None:
    ids = {c.provider_id for c in list_provider_capabilities(include_disabled=True)}
    assert "cloudflare_workers_ai" in ids


def test_list_capabilities_all_returns_five() -> None:
    caps = list_provider_capabilities(include_disabled=True)
    assert len(caps) == 5


# ---------------------------------------------------------------------------
# get_provider_capability — happy path
# ---------------------------------------------------------------------------


def test_get_capability_higgsfield_fields() -> None:
    cap = get_provider_capability("higgsfield")
    assert cap.provider_id == "higgsfield"
    assert cap.display_name == "Higgsfield"
    assert "image_to_video" in cap.capabilities
    assert cap.supports_webhooks is True
    assert cap.supports_polling is True
    assert cap.requires_api_key is True
    assert cap.has_free_tier is False
    assert cap.paid_side_effect_risk is True
    assert cap.requires_human_approval_for_execution is True
    assert cap.default_enabled is True


def test_get_capability_unknown_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown provider capability"):
        get_provider_capability("unknown_provider")


# ---------------------------------------------------------------------------
# Required fields — all enabled providers
# ---------------------------------------------------------------------------


def test_all_enabled_providers_have_required_fields() -> None:
    required_str_fields = ["provider_id", "display_name"]
    required_list_fields = ["modes", "capabilities"]
    for cap in list_provider_capabilities(include_disabled=False):
        for f in required_str_fields:
            assert isinstance(getattr(cap, f), str), f"{cap.provider_id}.{f} must be str"
        for f in required_list_fields:
            val = getattr(cap, f)
            assert isinstance(val, list) and len(val) > 0, (
                f"{cap.provider_id}.{f} must be non-empty list"
            )


# ---------------------------------------------------------------------------
# Safety invariants
# ---------------------------------------------------------------------------


def test_all_paid_providers_require_human_approval() -> None:
    """Every provider with paid_side_effect_risk=True must require human approval."""
    for cap in list_provider_capabilities(include_disabled=True):
        if cap.paid_side_effect_risk:
            assert cap.requires_human_approval_for_execution is True, (
                f"{cap.provider_id}: paid_side_effect_risk=True but "
                f"requires_human_approval=False"
            )


def test_manual_dashboard_has_no_paid_side_effect_risk() -> None:
    cap = get_provider_capability("manual_dashboard")
    assert cap.paid_side_effect_risk is False


def test_cloudflare_workers_ai_is_disabled_by_default() -> None:
    cap = get_provider_capability("cloudflare_workers_ai")
    assert cap.default_enabled is False


# ---------------------------------------------------------------------------
# get_all_provider_ids
# ---------------------------------------------------------------------------


def test_get_all_provider_ids_includes_disabled() -> None:
    ids = get_all_provider_ids(include_disabled=True)
    assert "cloudflare_workers_ai" in ids
    assert len(ids) == 5


def test_get_all_provider_ids_excludes_disabled_when_requested() -> None:
    ids = get_all_provider_ids(include_disabled=False)
    assert "cloudflare_workers_ai" not in ids
    assert len(ids) == 4


def test_get_all_provider_ids_returns_frozenset() -> None:
    ids = get_all_provider_ids()
    assert isinstance(ids, frozenset)
