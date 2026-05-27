"""Tests for MCP resources and prompts (Issue #60)."""

from unittest.mock import MagicMock

from vos_studio_mcp.resources.playbook import (
    _PLAYBOOK_OVERVIEW,
    _PROVIDER_GUIDE,
    _STAGE_CONTENT,
    register_resources_and_prompts,
)

# ---------------------------------------------------------------------------
# Content completeness
# ---------------------------------------------------------------------------


def test_stage_content_covers_all_stages() -> None:
    for stage in ("stage_0", "stage_a", "stage_b", "stage_c", "repair", "final"):
        assert stage in _STAGE_CONTENT
        content = _STAGE_CONTENT[stage]
        assert content  # non-empty
        assert "QA" in content or "criteria" in content.lower()
        assert "Next step" in content


def test_playbook_overview_contains_key_sections() -> None:
    assert "VOS Method" in _PLAYBOOK_OVERVIEW or "method" in _PLAYBOOK_OVERVIEW.lower()
    assert "9-Shot" in _PLAYBOOK_OVERVIEW or "9-shot" in _PLAYBOOK_OVERVIEW
    assert "Stage 0" in _PLAYBOOK_OVERVIEW
    assert "Stage C" in _PLAYBOOK_OVERVIEW
    assert "MCP Tool Workflow" in _PLAYBOOK_OVERVIEW


def test_provider_guide_covers_all_providers() -> None:
    for provider in ("Higgsfield", "Freepik", "Magnific", "Manual"):
        assert provider in _PROVIDER_GUIDE


def test_stage_c_content_mentions_9shot_structure() -> None:
    content = _STAGE_CONTENT["stage_c"]
    assert "9" in content
    assert "Establish" in content
    assert "Engage" in content
    assert "Convert" in content


def test_stage_0_content_mentions_anchor() -> None:
    content = _STAGE_CONTENT["stage_0"]
    assert "anchor" in content.lower()


def test_repair_content_mentions_source() -> None:
    content = _STAGE_CONTENT["repair"]
    assert "source_asset_id" in content


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def _make_mock_mcp() -> tuple[MagicMock, list[str], list[str]]:
    """Create a mock MCP that captures resource and prompt registrations."""
    registered_resources: list[str] = []
    registered_prompts: list[str] = []
    mock_mcp = MagicMock()

    def _resource(uri: str, **kwargs: object):  # type: ignore[override]
        registered_resources.append(uri)
        def decorator(fn: object) -> object:
            return fn
        return decorator

    def _prompt(**kwargs: object):  # type: ignore[override]
        name = kwargs.get("name", "unknown")
        registered_prompts.append(str(name))
        def decorator(fn: object) -> object:
            return fn
        return decorator

    mock_mcp.resource = _resource
    mock_mcp.prompt = _prompt
    return mock_mcp, registered_resources, registered_prompts


def test_register_all_stage_resources() -> None:
    mock_mcp, resources, _ = _make_mock_mcp()
    register_resources_and_prompts(mock_mcp)  # type: ignore[arg-type]

    expected_uris = {
        "vos://playbook",
        "vos://stage-templates/stage_0",
        "vos://stage-templates/stage_a",
        "vos://stage-templates/stage_b",
        "vos://stage-templates/stage_c",
        "vos://stage-templates/repair",
        "vos://stage-templates/final",
        "vos://providers",
    }
    assert expected_uris.issubset(set(resources))


def test_register_prompts() -> None:
    mock_mcp, _, prompts = _make_mock_mcp()
    register_resources_and_prompts(mock_mcp)  # type: ignore[arg-type]

    assert "vos_creative_brief" in prompts
    assert "vos_shot_direction" in prompts


# ---------------------------------------------------------------------------
# Prompt template output
# ---------------------------------------------------------------------------


def test_creative_brief_prompt_contains_product() -> None:
    from vos_studio_mcp.resources.playbook import vos_creative_brief

    result = vos_creative_brief(
        brand_name="TestCo",
        product="SuperApp",
        target_audience="Gen-Z",
        campaign_objective="Drive downloads",
    )
    # Since vos_creative_brief is defined inside register_resources_and_prompts,
    # we need to get it differently. Just test the module-level content is correct.
    assert "SuperApp" in result or "TestCo" in result


def test_creative_brief_includes_workflow_steps() -> None:
    from vos_studio_mcp.resources.playbook import vos_creative_brief

    result = vos_creative_brief(
        brand_name="TestCo",
        product="SuperApp",
        target_audience="Gen-Z",
        campaign_objective="Drive downloads",
    )
    assert "save_brand_kit" in result or "prepare_video_blueprint" in result


def test_shot_direction_contains_shot_number() -> None:
    from vos_studio_mcp.resources.playbook import vos_shot_direction

    result = vos_shot_direction(
        shot_number=3,
        role="close-up detail",
        camera_movement="Close-up hold with subtle zoom",
        product="SuperApp",
        target_audience="Gen-Z",
    )
    assert "3" in result
    assert "SuperApp" in result
    assert "Close-up" in result or "close-up" in result
