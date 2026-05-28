"""Unit tests for get_workflow_guide service."""

import pytest


def test_generate_video_returns_ordered_steps() -> None:
    from vos_studio_mcp.services.workflow_guide_service import get_workflow_guide

    result = get_workflow_guide("generate_video")

    assert result.status == "ok"
    assert result.goal == "generate_video"
    assert result.total_steps == len(result.steps)
    assert result.steps[0].step == 1
    # Steps must be sequential
    for i, step in enumerate(result.steps, start=1):
        assert step.step == i
    # check_generation_readiness must be in the generate_video flow
    tool_names = [s.tool for s in result.steps]
    assert "check_generation_readiness" in tool_names
    assert "request_api_video" in tool_names
    assert result.next_action == result.steps[0].tool


def test_all_goals_return_valid_response() -> None:
    from vos_studio_mcp.services.workflow_guide_service import (
        get_workflow_guide,
        list_available_goals,
    )

    for goal in list_available_goals():
        result = get_workflow_guide(goal)
        assert result.status == "ok"
        assert result.total_steps > 0
        assert result.next_action != ""
        for step in result.steps:
            assert step.tool != ""
            assert len(step.required_inputs) >= 0


def test_unknown_goal_raises_vos_error() -> None:
    from vos_studio_mcp.errors import ErrorCode, VosError
    from vos_studio_mcp.services.workflow_guide_service import get_workflow_guide

    with pytest.raises(VosError) as exc:
        get_workflow_guide("nonexistent_goal")

    assert exc.value.error_code == ErrorCode.INVALID_INPUT
    assert "nonexistent_goal" in str(exc.value)


def test_onboard_client_starts_with_create_client() -> None:
    from vos_studio_mcp.services.workflow_guide_service import get_workflow_guide

    result = get_workflow_guide("onboard_client")
    assert result.steps[0].tool == "create_client"


def test_list_available_goals_is_non_empty() -> None:
    from vos_studio_mcp.services.workflow_guide_service import list_available_goals

    goals = list_available_goals()
    assert len(goals) >= 5
    assert "generate_video" in goals
    assert "onboard_client" in goals
