from vos_studio_mcp.services.providers.capabilities import (
    get_provider_capability,
    list_provider_capabilities,
)


def test_list_provider_capabilities_covers_current_providers() -> None:
    providers = list_provider_capabilities()
    provider_ids = {provider.provider_id for provider in providers}

    assert provider_ids == {"freepik", "higgsfield", "magnific", "manual_dashboard"}


def test_provider_capabilities_include_expected_safety_metadata() -> None:
    freepik = get_provider_capability("freepik")
    manual_dashboard = get_provider_capability("manual_dashboard")

    assert "text_to_image" in freepik.capabilities
    assert freepik.requires_api_key is True
    assert freepik.paid_side_effect_risk is True
    assert freepik.requires_human_approval_for_execution is True

    assert manual_dashboard.modes == ["dashboard_manual"]
    assert manual_dashboard.requires_api_key is False
    assert manual_dashboard.paid_side_effect_risk is False


def test_unknown_provider_capability_raises_value_error() -> None:
    try:
        get_provider_capability("unknown")
    except ValueError as exc:
        assert "Unknown provider capability" in str(exc)
    else:
        raise AssertionError("expected ValueError for unknown provider")
