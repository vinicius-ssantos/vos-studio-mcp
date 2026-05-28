"""Static workflow guide definitions — returns step-by-step tool sequences per goal."""

from typing import Any

from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.schemas.workflow_guide import WorkflowGuideResponse, WorkflowStep

_WORKFLOWS: dict[str, dict[str, Any]] = {
    "generate_video": {
        "description": (
            "Full API-based video generation workflow: sprint setup → generation → "
            "QA → delivery."
        ),
        "steps": [
            WorkflowStep(
                step=1, tool="create_client",
                purpose="Register the client if not yet created.",
                required_inputs=["client_name"],
            ),
            WorkflowStep(
                step=2, tool="save_brand_kit",
                purpose="Define brand identity (tone, colors, references) for the sprint.",
                required_inputs=["client_id", "brand_name"],
            ),
            WorkflowStep(
                step=3, tool="prepare_creative_brief",
                purpose="Generate a structured creative brief from the campaign objective.",
                required_inputs=["client_id", "campaign_objective", "target_audience"],
            ),
            WorkflowStep(
                step=4, tool="create_creative_sprint",
                purpose="Open a sprint with budget and generation limits.",
                required_inputs=["client_id", "product_name", "budget.max_spend_usd"],
            ),
            WorkflowStep(
                step=5, tool="check_generation_readiness",
                purpose="Validate provider health, budget, and token before committing to generation.",
                required_inputs=["provider", "sprint_id", "client_id"],
                notes="Skippable if you are confident about provider state.",
            ),
            WorkflowStep(
                step=6, tool="prepare_video_blueprint",
                purpose="Generate versioned prompt and preset for the video.",
                required_inputs=["sprint_id", "brief"],
            ),
            WorkflowStep(
                step=7, tool="request_api_video",
                purpose="Submit generation job to the provider. Requires approval_token.",
                required_inputs=["sprint_id", "client_id", "prompt", "approval_token", "provider"],
            ),
            WorkflowStep(
                step=8, tool="get_video_job_status",
                purpose="Poll generation and storage status until completed.",
                required_inputs=["asset_id"],
                notes="Poll every 30s. Status transitions: pending → processing → completed.",
            ),
            WorkflowStep(
                step=9, tool="review_asset_quality",
                purpose="Run QA check and set qa_status (approved/needs_repair/rejected).",
                required_inputs=["asset_id", "client_id"],
            ),
            WorkflowStep(
                step=10, tool="prepare_dashboard_pack",
                purpose="Generate operator delivery pack with settings and QA criteria.",
                required_inputs=["sprint_id", "prompt_version", "preset_version"],
            ),
            WorkflowStep(
                step=11, tool="close_sprint",
                purpose="Close the sprint after all assets are approved.",
                required_inputs=["sprint_id", "client_id"],
            ),
        ],
    },
    "register_manual_asset": {
        "description": (
            "Dashboard-manual workflow: VOS prepares packs; operator generates outside VOS "
            "and registers the result."
        ),
        "steps": [
            WorkflowStep(
                step=1, tool="create_creative_sprint",
                purpose="Open a sprint in dashboard_manual mode.",
                required_inputs=["client_id", "product_name", "budget.max_spend_usd"],
            ),
            WorkflowStep(
                step=2, tool="prepare_dashboard_pack",
                purpose="Generate the prompt, settings, and checklist for the operator.",
                required_inputs=["sprint_id", "prompt_version", "preset_version"],
            ),
            WorkflowStep(
                step=3, tool="register_manual_asset",
                purpose="Register the asset that the operator generated outside VOS.",
                required_inputs=["sprint_id", "storage_url", "provider"],
            ),
            WorkflowStep(
                step=4, tool="review_asset_quality",
                purpose="QA the registered asset.",
                required_inputs=["asset_id", "client_id"],
            ),
            WorkflowStep(
                step=5, tool="close_sprint",
                purpose="Close the sprint.",
                required_inputs=["sprint_id", "client_id"],
            ),
        ],
    },
    "onboard_client": {
        "description": "First-time client setup: create client, configure brand kit, first sprint.",
        "steps": [
            WorkflowStep(
                step=1, tool="create_client",
                purpose="Create the client record.",
                required_inputs=["client_name"],
            ),
            WorkflowStep(
                step=2, tool="save_brand_kit",
                purpose="Define brand identity, tone of voice, and visual references.",
                required_inputs=["client_id", "brand_name", "tone_of_voice"],
            ),
            WorkflowStep(
                step=3, tool="prepare_creative_brief",
                purpose="Generate the first creative brief.",
                required_inputs=["client_id", "campaign_objective", "target_audience"],
            ),
            WorkflowStep(
                step=4, tool="create_creative_sprint",
                purpose="Open the first sprint.",
                required_inputs=["client_id", "product_name", "budget.max_spend_usd"],
            ),
        ],
    },
    "review_and_approve_assets": {
        "description": "QA and approval flow for assets in an existing sprint.",
        "steps": [
            WorkflowStep(
                step=1, tool="list_sprint_assets",
                purpose="List all assets in the sprint filtered by needs_review.",
                required_inputs=["sprint_id", "client_id"],
            ),
            WorkflowStep(
                step=2, tool="review_asset_quality",
                purpose="Review each asset and set qa_status.",
                required_inputs=["asset_id", "client_id"],
                notes="Repeat for each asset. approved → ready for delivery; needs_repair → re-generate.",
            ),
            WorkflowStep(
                step=3, tool="get_sprint_status",
                purpose="Check overall sprint progress and how many assets are approved.",
                required_inputs=["sprint_id", "client_id"],
            ),
            WorkflowStep(
                step=4, tool="close_sprint",
                purpose="Close when all required assets are approved.",
                required_inputs=["sprint_id", "client_id"],
            ),
        ],
    },
    "performance_feedback": {
        "description": "Record post-distribution performance metrics to close the creative learning loop.",
        "steps": [
            WorkflowStep(
                step=1, tool="list_sprint_assets",
                purpose="Identify the final approved assets from the sprint.",
                required_inputs=["sprint_id", "client_id"],
            ),
            WorkflowStep(
                step=2, tool="record_performance_metrics",
                purpose="Log distribution metrics (impressions, CTR, ROAS) for each asset.",
                required_inputs=["asset_id", "platform", "metrics"],
            ),
            WorkflowStep(
                step=3, tool="get_sprint_performance_summary",
                purpose="Review aggregated performance for the sprint.",
                required_inputs=["sprint_id", "client_id"],
            ),
            WorkflowStep(
                step=4, tool="promote_to_library",
                purpose="Promote top-performing assets to the cross-client prompt library.",
                required_inputs=["asset_id", "client_id"],
                notes="Only approved assets with high performance labels are eligible.",
            ),
            WorkflowStep(
                step=5, tool="refresh_library_tiers",
                purpose="Recompute library tier rankings after new promotions.",
                required_inputs=["client_id"],
            ),
        ],
    },
}

_AVAILABLE_GOALS = sorted(_WORKFLOWS.keys())


def get_workflow_guide(goal: str) -> WorkflowGuideResponse:
    if goal not in _WORKFLOWS:
        raise VosError(
            ErrorCode.INVALID_INPUT,
            f"Unknown goal '{goal}'. Available goals: {', '.join(_AVAILABLE_GOALS)}.",
        )
    wf = _WORKFLOWS[goal]
    steps: list[WorkflowStep] = wf["steps"]
    description: str = wf["description"]
    return WorkflowGuideResponse(
        status="ok",
        goal=goal,
        description=description,
        steps=steps,
        total_steps=len(steps),
        summary=f"Workflow '{goal}': {len(steps)} steps. Start with '{steps[0].tool}'.",
        next_action=steps[0].tool,
    )


def list_available_goals() -> list[str]:
    return _AVAILABLE_GOALS
