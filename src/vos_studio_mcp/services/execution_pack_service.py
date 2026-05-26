"""Execution pack service — stage-aware operator guidance (Issue #55).

Pure composition: no external API calls, no paid side-effects.
Each stage maps to a structured operator workflow with explicit QA criteria.
"""

import logging
import uuid

from db.models import BrandKit, Sprint
from vos_studio_mcp.auth.guards import assert_owns_client
from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.schemas.asset import _ASSET_STAGE_LABELS
from vos_studio_mcp.schemas.execution_pack import (
    ExecutionPackResponse,
    ExecutionStep,
    PrepareExecutionPackInput,
)
from vos_studio_mcp.services.database import get_session, set_tenant_context

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stage-specific operator workflows
# ---------------------------------------------------------------------------

_STAGE_OBJECTIVES: dict[str, str] = {
    "stage_0": "Produce the campaign anchor image: the single reference frame that locks visual identity.",
    "stage_a": "Produce the character sheet: all talent/character reference angles for the campaign.",
    "stage_b": "Produce the storyboard: pre-visualization frames aligned to the shot plan.",
    "stage_c": "Produce the final video: animated clips per shot plan, assembled to delivery spec.",
    "repair": "Produce a repair variant: a corrected version of a rejected or flagged asset.",
    "final": "Prepare and register the final delivery asset: the approved sprint deliverable.",
}

_STAGE_STEPS: dict[str, list[tuple[str, str, str | None]]] = {
    # (action, details, qa_check)
    "stage_0": [
        (
            "Load brand kit",
            "Open brand kit: review identity, primary/secondary colors, and style keywords.",
            "Confirm palette and tone match the brief.",
        ),
        (
            "Generate anchor image",
            "Use approved reference imagery and brand color palette. Prompt: cinematic, on-brand, "
            "single dominant subject, no text.",
            "Product centered, colors match palette, no watermarks, no text.",
        ),
        (
            "QA anchor image",
            "Check resolution ≥ 1080p, no artifacts, product clearly legible on mobile.",
            "Pass: register as asset_stage=stage_0, approved_as_reference=true.",
        ),
        (
            "Register anchor",
            "Register via register_manual_asset with asset_stage=stage_0, asset_kind=manual, "
            "approved_as_reference=true.",
            None,
        ),
    ],
    "stage_a": [
        (
            "Source talent references",
            "Collect approved talent/character references from asset library or new capture.",
            "References match campaign brief (age, look, environment).",
        ),
        (
            "Generate character angles",
            "Produce front/3-quarter/side angles using Stage 0 anchor as visual reference.",
            "Consistent lighting, palette, and expression across all angles.",
        ),
        (
            "QA character sheet",
            "Check: face legible on mobile, no brand violations, natural pose, no artifacts.",
            "Pass: register all approved angles as asset_stage=stage_a.",
        ),
        (
            "Register character assets",
            "Register each angle via register_manual_asset with asset_stage=stage_a, "
            "source_asset_id pointing to the Stage 0 anchor.",
            None,
        ),
    ],
    "stage_b": [
        (
            "Load shot plan",
            "Open the video blueprint shot plan. Each shot defines scene, camera movement, "
            "pacing, and keyframe guidance.",
            "Shot plan matches campaign brief and product.",
        ),
        (
            "Generate storyboard frames",
            "For each shot in the plan, produce one keyframe that matches scene description, "
            "camera angle, and pacing note.",
            "Each frame: correct subject scale, camera angle, no artifacts.",
        ),
        (
            "Review storyboard sequence",
            "Check visual flow: alternates scale (wide → medium → close-up), maintains "
            "brand palette, narrative arc is clear.",
            "Sequence approved: all 9 frames present, scale alternation correct.",
        ),
        (
            "Register storyboard",
            "Register each frame via register_manual_asset with asset_stage=stage_b, "
            "source_asset_id pointing to the relevant Stage 0 or Stage A asset.",
            None,
        ),
    ],
    "stage_c": [
        (
            "Prepare provider workspace",
            "Open provider dashboard. Upload Stage 0 anchor image as reference. "
            "Confirm model, aspect ratio, and duration settings match blueprint.",
            "Reference image loaded, settings match execution pack.",
        ),
        (
            "Execute shots per blueprint",
            "Generate each shot using the motion prompt and keyframe guidance from the shot plan. "
            "Do not deviate from motion prompts or camera movements.",
            "Each clip: correct duration, motion direction, no artifacts.",
        ),
        (
            "QA each clip",
            "Review: resolution matches spec, brand palette present, product visible, "
            "no competitor branding, pacing matches shot plan.",
            "All clips pass QA before proceeding to assembly.",
        ),
        (
            "Assemble and export",
            "Assemble clips in storyboard order. Export MP4 H.264 at 1080p minimum.",
            "Final video: correct total duration, clean transitions, no artifacts.",
        ),
        (
            "Register video asset",
            "Register via register_manual_asset with asset_stage=stage_c, asset_kind=generated, "
            "source_asset_id pointing to Stage B storyboard.",
            None,
        ),
    ],
    "repair": [
        (
            "Identify source asset",
            "Locate the rejected/flagged asset. Note the specific failure criteria from QA.",
            "Source asset and failure reason confirmed.",
        ),
        (
            "Diagnose and plan correction",
            "Map failure criteria to root cause: wrong motion, palette drift, product off-center, "
            "artifact, etc. Define the minimal correction.",
            "Correction plan does not require full re-generation.",
        ),
        (
            "Execute repair",
            "Re-generate or edit addressing only the identified failure. Use same motion prompt "
            "and settings as original unless the prompt was the root cause.",
            "Repair addresses the original failure without introducing new issues.",
        ),
        (
            "QA repair against original criteria",
            "Re-run all QA checks that failed in the original asset.",
            "All previously failing criteria now pass.",
        ),
        (
            "Register repair variant",
            "Register via register_manual_asset with asset_stage=repair, "
            "source_asset_id pointing to the original rejected asset.",
            None,
        ),
    ],
    "final": [
        (
            "Assemble final deliverable",
            "Collect all approved Stage C clips and any approved Stage A/B references. "
            "Confirm all QA checks are complete.",
            "All assets registered, no pending QA flags.",
        ),
        (
            "Final export",
            "Export to delivery spec: MP4 H.264, 1080p minimum, correct aspect ratio, "
            "total duration within brief.",
            "Export matches delivery specification exactly.",
        ),
        (
            "Final QA",
            "Run complete QA pass: product consistency, label accuracy, mobile readability, "
            "endcard correct, no risky claims, brand restrictions respected.",
            "All QA criteria pass. No blockers.",
        ),
        (
            "Register final delivery",
            "Register via register_manual_asset with asset_stage=final, "
            "is_final_delivery=true, approved_as_reference=true.",
            None,
        ),
    ],
}

_STAGE_QA_CRITERIA: dict[str, list[str]] = {
    "stage_0": [
        "Product/subject centered and clearly visible",
        "Brand color palette applied",
        "Resolution ≥ 1080p, no artifacts",
        "No text, watermarks, or competitor branding",
        "Mobile-legible on 375px wide viewport",
    ],
    "stage_a": [
        "Consistent lighting and palette across all angles",
        "Face/talent clearly legible on mobile",
        "No brand violations (no forbidden elements)",
        "Natural pose and expression — no generic stock look",
        "Correct aspect ratio for intended placement",
    ],
    "stage_b": [
        "Each frame matches shot plan scene description",
        "Camera angle matches blueprint camera_movement",
        "Scale alternation: wide → medium → close-up across sequence",
        "Brand palette maintained in all frames",
        "No artifacts, no text in frames (unless CTA shot)",
    ],
    "stage_c": [
        "Each clip duration matches shot plan (±0.5 s)",
        "Motion direction matches blueprint camera_movement",
        "Product visible and correctly positioned throughout",
        "Brand color palette present in all clips",
        "No artifacts, blur, or compression issues at 1080p",
        "Pacing matches block (slow-burn / mid-pace / energetic)",
        "No competitor branding, no watermarks",
        "Final assembly: correct total duration, clean transitions",
    ],
    "repair": [
        "All previously failing QA criteria now pass",
        "No new issues introduced by the repair",
        "Motion prompt and style consistent with original",
        "Repair is the minimal change needed — no scope creep",
    ],
    "final": [
        "Product consistency verified end-to-end",
        "Label accuracy: all text/on-screen labels correct",
        "Campaign coherence: narrative arc is clear",
        "Mobile readability at 375px",
        "Endcard correct: CTA legible, brand mark visible",
        "No risky claims or policy violations",
        "Export matches delivery specification (resolution, codec, duration)",
    ],
}

_STAGE_OUTPUT_SPECS: dict[str, dict[str, object]] = {
    "stage_0": {"format": "JPEG/PNG", "resolution": "1080p minimum", "aspect_ratio": "16:9"},
    "stage_a": {
        "format": "JPEG/PNG",
        "resolution": "1080p minimum",
        "angles": "front, 3-quarter, side",
    },
    "stage_b": {
        "format": "JPEG/PNG",
        "resolution": "1080p minimum",
        "frames": "one per shot in plan",
    },
    "stage_c": {"format": "MP4 H.264", "resolution": "1080p minimum", "codec": "H.264"},
    "repair": {"format": "match original", "resolution": "match original"},
    "final": {
        "format": "MP4 H.264",
        "resolution": "1080p minimum",
        "codec": "H.264",
        "export": "delivery spec",
    },
}

_STAGE_NEXT_ACTIONS: dict[str, str] = {
    "stage_0": "register_manual_asset",
    "stage_a": "register_manual_asset",
    "stage_b": "register_manual_asset",
    "stage_c": "register_manual_asset",
    "repair": "review_asset_quality",
    "final": "register_manual_asset",
}


# ---------------------------------------------------------------------------
# Public service function
# ---------------------------------------------------------------------------


async def prepare_execution_pack(data: PrepareExecutionPackInput) -> ExecutionPackResponse:
    """Compose a stage-aware execution pack from sprint and brand kit context."""
    sprint_uuid = uuid.UUID(data.sprint_id)

    async with get_session() as session:
        sprint: Sprint | None = await session.get(Sprint, sprint_uuid)
        if sprint is None:
            raise VosError(ErrorCode.NOT_FOUND, f"Sprint {data.sprint_id} not found")

        assert_owns_client(str(sprint.client_id))
        await set_tenant_context(session, str(sprint.client_id))
        brand_kit: BrandKit | None = await session.get(BrandKit, sprint.brand_kit_id)

    if sprint.sprint_status != "open":
        return ExecutionPackResponse(
            status="blocked",
            sprint_id=data.sprint_id,
            asset_stage=data.asset_stage,
            asset_stage_label=_ASSET_STAGE_LABELS.get(data.asset_stage, data.asset_stage),
            provider=data.provider,
            mode=data.mode,
            objective="",
            operator_steps=[],
            qa_criteria=[],
            negative_constraints=[],
            output_spec={},
            summary=f"Sprint is {sprint.sprint_status} — execution pack not available.",
            next_action=f"sprint_is_{sprint.sprint_status}",
        )

    restrictions = brand_kit.restrictions if brand_kit else {}
    objective = _build_stage_objective(data.asset_stage, sprint)
    steps = _build_operator_steps(data.asset_stage, sprint, brand_kit)
    qa_criteria = list(_STAGE_QA_CRITERIA.get(data.asset_stage, []))
    negative_constraints = _build_negative_constraints(restrictions)
    output_spec = dict(_STAGE_OUTPUT_SPECS.get(data.asset_stage, {}))
    output_spec["prompt_version"] = data.prompt_version
    output_spec["preset_version"] = data.preset_version
    stage_label = _ASSET_STAGE_LABELS.get(data.asset_stage, data.asset_stage)

    log.info(
        "execution pack prepared",
        extra={
            "sprint_id": data.sprint_id,
            "asset_stage": data.asset_stage,
            "provider": data.provider,
            "mode": data.mode,
        },
    )

    return ExecutionPackResponse(
        status="ready",
        sprint_id=data.sprint_id,
        asset_stage=data.asset_stage,
        asset_stage_label=stage_label,
        provider=data.provider,
        mode=data.mode,
        objective=objective,
        operator_steps=steps,
        qa_criteria=qa_criteria,
        negative_constraints=negative_constraints,
        output_spec=output_spec,
        summary=(
            f"Execution pack ready for {stage_label}: "
            f"{len(steps)} steps, {len(qa_criteria)} QA criteria."
        ),
        next_action=_STAGE_NEXT_ACTIONS.get(data.asset_stage, "register_manual_asset"),
    )


# ---------------------------------------------------------------------------
# Composition helpers (pure functions — no I/O)
# ---------------------------------------------------------------------------


def _build_stage_objective(stage: str, sprint: Sprint) -> str:
    base = _STAGE_OBJECTIVES.get(stage, "Execute this production stage.")
    return f"{base} Product: {sprint.product_name}. Audience: {sprint.target_audience}."


def _build_operator_steps(
    stage: str, sprint: Sprint, brand_kit: BrandKit | None
) -> list[ExecutionStep]:
    raw_steps = _STAGE_STEPS.get(stage, [])
    identity = brand_kit.identity if brand_kit else {}
    visual = brand_kit.visual if brand_kit else {}

    raw_primary = visual.get("primary_colors")
    raw_secondary = visual.get("secondary_colors")
    primary = list(raw_primary) if isinstance(raw_primary, list) else []
    secondary = list(raw_secondary) if isinstance(raw_secondary, list) else []
    all_colors = primary + secondary
    color_palette = ", ".join(str(c) for c in all_colors[:3]) if all_colors else "brand palette"

    raw_tone = identity.get("tone")
    if isinstance(raw_tone, list) and raw_tone:
        tone = ", ".join(str(t) for t in raw_tone)
    elif isinstance(raw_tone, str) and raw_tone:
        tone = raw_tone
    else:
        tone = "authentic and engaging"

    steps: list[ExecutionStep] = []
    for i, (action, details, qa_check) in enumerate(raw_steps, start=1):
        expanded_details = details.format(
            product=sprint.product_name,
            audience=sprint.target_audience,
            palette=color_palette,
            tone=tone,
        ) if "{product}" in details or "{palette}" in details or "{tone}" in details else details

        steps.append(
            ExecutionStep(
                step_number=i,
                action=action,
                details=expanded_details,
                qa_check=qa_check,
            )
        )
    return steps


def _build_negative_constraints(restrictions: dict[str, object]) -> list[str]:
    base = [
        "No competitor branding or logos",
        "No watermarks or text overlays (except CTA in stage_c shot 8)",
        "No distorted proportions or artifacts",
        "No low-resolution or blurry output",
        "No forbidden elements from brand restrictions",
    ]
    forbidden_elements: object = restrictions.get("forbidden_elements")
    if isinstance(forbidden_elements, list):
        base.extend(str(f) for f in forbidden_elements)
    elif isinstance(forbidden_elements, str) and forbidden_elements:
        base.append(forbidden_elements)
    return base
