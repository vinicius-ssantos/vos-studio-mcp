"""Video blueprint service — composes a director-level blueprint from sprint + brand kit (issue #13).

Pure composition: no external API calls, no paid side-effects.
"""

import logging
import uuid

from db.models import BrandKit, Sprint
from vos_studio_mcp.auth.guards import assert_owns_client
from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.schemas.blueprint import (
    ProviderExecutionPack,
    ShotPlan,
    VideoBlueprintInput,
    VideoBlueprintResponse,
)
from vos_studio_mcp.services.audit_service import AuditAction, AuditResult, emit_audit_event
from vos_studio_mcp.services.database import get_session, set_tenant_context

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider-specific defaults
# ---------------------------------------------------------------------------

_PROVIDER_MODELS: dict[str, str] = {
    "higgsfield": "Higgsfield Animate v1",
    "freepik": "Freepik Mystic v2",
    "magnific": "Magnific Upscale+Motion",
    "manual": "Dashboard Manual",
}

_PROVIDER_BASE_SETTINGS: dict[str, dict[str, object]] = {
    "higgsfield": {"aspect_ratio": "16:9", "duration_seconds": 5, "resolution": "720p"},
    "freepik": {"style": "cinematic", "color_grading": "natural", "resolution": "1080p"},
    "magnific": {"scale_factor": 2, "creativity": 0.5, "resemblance": 0.8},
    "manual": {"format": "MP4", "resolution": "1080p", "codec": "H.264"},
}

_PROVIDER_CHECKLISTS: dict[str, list[str]] = {
    "higgsfield": [
        "Upload reference image to Higgsfield project",
        "Paste motion prompt and confirm model selection",
        "Set duration and resolution as specified",
        "Review preview frame before confirming generation",
        "Download MP4 and upload to asset registry",
    ],
    "freepik": [
        "Open Freepik AI video workspace",
        "Select Mystic model and cinematic style",
        "Paste adapted prompt; adjust color grading slider",
        "Run generation and verify style consistency with brand kit",
        "Export at 1080p and register asset",
    ],
    "magnific": [
        "Upload source frame to Magnific",
        "Set scale factor 2x and creativity/resemblance sliders",
        "Apply motion effect with pacing from shot plan",
        "Download enhanced clip and register asset",
    ],
    "manual": [
        "Share shot plan and motion prompts with videographer",
        "Brief talent/crew on camera movement and pacing notes",
        "Capture per shot plan; verify keyframe guidance on set",
        "Edit according to pacing spec; export MP4 H.264 1080p",
        "QA against brand restrictions before registering asset",
    ],
}

_CAMERA_MOVEMENTS = [
    "Slow push-in",
    "Static wide establishing",
    "Tracking shot left-to-right",
    "Aerial pull-back",
    "Close-up hold with subtle zoom",
    "Pan right to product reveal",
    "Crane down to subject",
    "Dutch angle into hero product",
    "Rack focus from background to foreground",
    "Handheld walk-and-talk",
]

_PACING_OPTIONS = ["slow-burn (4–6 s)", "mid-pace (2–4 s)", "energetic (1–2 s)"]

# ---------------------------------------------------------------------------
# VOS 9-shot structure constant and data
# ---------------------------------------------------------------------------

VOS_DEFAULT_SHOT_COUNT = 9

# Block definitions: (block_name, pacing, list of (role, camera_movement, scene_suffix, keyframe_note))
_VOS_SHOT_BLOCKS: list[tuple[str, str, list[tuple[str, str, str, str]]]] = [
    (
        "Establish",
        "slow-burn",
        [
            (
                "wide establishing shot",
                "Static wide establishing",
                "opening wide establishing frame — set location and atmosphere",
                "Frame wide; keep {product} anchored in mid-ground with environment context.",
            ),
            (
                "medium product reveal",
                "Pan right to product reveal",
                "medium-shot reveal of {product} for {audience}",
                "Lead the eye to {product}; hero it centrally at medium distance.",
            ),
            (
                "close-up detail",
                "Close-up hold with subtle zoom",
                "close-up detail shot highlighting key feature of {product}",
                "Fill frame with the most distinctive feature; maintain {palette} palette.",
            ),
        ],
    ),
    (
        "Engage",
        "mid-pace",
        [
            (
                "medium lifestyle/context",
                "Tracking shot left-to-right",
                "medium lifestyle shot — {product} in context for {audience}",
                "Show {audience} interacting naturally with {product}; authentic environment.",
            ),
            (
                "close-up emotional",
                "Rack focus from background to foreground",
                "close-up emotional beat — human response to {product}",
                "Rack focus to subject's face or hands; convey emotion, not just product.",
            ),
            (
                "wide action/use",
                "Aerial pull-back",
                "wide action shot — {product} in full use for {audience}",
                "Pull back to reveal full scene; reinforce scale and energy of the moment.",
            ),
        ],
    ),
    (
        "Convert",
        "energetic",
        [
            (
                "medium social proof/result",
                "Slow push-in",
                "medium social proof or result shot for {product}",
                "Show result or transformation; reinforce credibility with visual evidence.",
            ),
            (
                "close-up CTA element",
                "Close-up hold with subtle zoom",
                "close-up CTA element — call-to-action detail for {product}",
                "Isolate CTA element (pack, screen, label); must be legible on mobile.",
            ),
            (
                "wide brand close",
                "Crane down to subject",
                "wide brand closing shot — {product} brand signature for {audience}",
                "Close on brand mark or hero product in a clean wide frame; {palette} dominant.",
            ),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Public service function
# ---------------------------------------------------------------------------


async def prepare_video_blueprint(data: VideoBlueprintInput) -> VideoBlueprintResponse:
    """Compose a director-level video blueprint from sprint and brand kit context.

    Loads sprint + brand_kit from the DB; builds shot plan, provider packs,
    and production checklists without calling any paid external API.
    """
    sprint_uuid = uuid.UUID(data.sprint_id)

    async with get_session() as session:
        sprint: Sprint | None = await session.get(Sprint, sprint_uuid)
        if sprint is None:
            raise VosError(ErrorCode.NOT_FOUND, f"Sprint {data.sprint_id} not found")

        # Verify the authenticated caller owns the sprint's client (ADR-0019, Issue #46).
        assert_owns_client(str(sprint.client_id))
        await set_tenant_context(session, str(sprint.client_id))
        brand_kit: BrandKit | None = await session.get(BrandKit, sprint.brand_kit_id)

    if sprint.sprint_status != "open":
        log.warning(
            "blueprint requested for non-open sprint",
            extra={"sprint_id": data.sprint_id, "sprint_status": sprint.sprint_status},
        )
        return VideoBlueprintResponse(
            status="blocked",
            sprint_id=data.sprint_id,
            creative_intent="",
            campaign_objective=sprint.campaign_objective,
            shot_plan=[],
            negative_prompts=[],
            provider_packs=[],
            manual_checklist=[],
            cost_notes="",
            risk_notes="",
            approval_required=False,
            summary=f"Sprint is {sprint.sprint_status} — blueprint not available.",
            next_action=f"sprint_is_{sprint.sprint_status}",
        )

    restrictions = brand_kit.restrictions if brand_kit else {}
    identity = brand_kit.identity if brand_kit else {}
    visual = brand_kit.visual if brand_kit else {}

    creative_intent = _build_creative_intent(sprint, identity)
    shot_plan = _build_shot_plan(sprint, data.shot_count, visual)
    negative_prompts = _build_negative_prompts(restrictions)
    provider_packs = _build_provider_packs(sprint, data, shot_plan, negative_prompts)
    manual_checklist = _build_manual_checklist(sprint, data)
    cost_notes = _build_cost_notes(sprint)
    risk_notes = _build_risk_notes(sprint, brand_kit)
    approval_required = sprint.spent_usd >= sprint.max_spend_usd * sprint.alert_threshold_pct

    await emit_audit_event(
        action=AuditAction.BLUEPRINT_PREPARED,
        entity_type="sprint",
        entity_id=data.sprint_id,
        mode=sprint.mode,
        result=AuditResult.SUCCESS,
    )
    log.info(
        "video blueprint prepared",
        extra={
            "sprint_id": data.sprint_id,
            "shot_count": len(shot_plan),
            "provider_targets": list(data.provider_targets),
        },
    )

    return VideoBlueprintResponse(
        status="ready",
        sprint_id=data.sprint_id,
        creative_intent=creative_intent,
        campaign_objective=sprint.campaign_objective,
        shot_plan=shot_plan,
        negative_prompts=negative_prompts,
        provider_packs=provider_packs,
        manual_checklist=manual_checklist,
        cost_notes=cost_notes,
        risk_notes=risk_notes,
        approval_required=approval_required,
        summary=(
            f"Blueprint ready for '{sprint.product_name}': "
            f"{len(shot_plan)} shots across {len(provider_packs)} provider(s)."
        ),
        next_action="prepare_dashboard_pack" if not approval_required else "review_budget_before_generating",
    )


# ---------------------------------------------------------------------------
# Composition helpers (pure functions — no I/O)
# ---------------------------------------------------------------------------


def _build_creative_intent(sprint: Sprint, identity: dict[str, object]) -> str:
    raw_tone = identity.get("tone")
    if isinstance(raw_tone, list) and raw_tone:
        tone: str = ", ".join(str(t) for t in raw_tone)
    elif isinstance(raw_tone, str) and raw_tone:
        tone = raw_tone
    else:
        tone = "authentic and engaging"
    return (
        f"Produce a {tone} video showcasing {sprint.product_name} "
        f"to {sprint.target_audience}. "
        f"Objective: {sprint.campaign_objective}."
    )


def _build_shot_plan(sprint: Sprint, shot_count: int, visual: dict[str, object]) -> list[ShotPlan]:
    raw_primary = visual.get("primary_colors")
    raw_secondary = visual.get("secondary_colors")
    primary: list[object] = list(raw_primary) if isinstance(raw_primary, list) else []
    secondary: list[object] = list(raw_secondary) if isinstance(raw_secondary, list) else []
    all_colors = primary + secondary
    color_palette = ", ".join(str(c) for c in all_colors[:3]) if all_colors else "brand palette"

    if shot_count == VOS_DEFAULT_SHOT_COUNT:
        return _build_vos_9shot_plan(sprint, color_palette)

    brief_words = sprint.brief.split()
    shots: list[ShotPlan] = []
    for i in range(1, shot_count + 1):
        movement = _CAMERA_MOVEMENTS[(i - 1) % len(_CAMERA_MOVEMENTS)]
        pacing = _PACING_OPTIONS[(i - 1) % len(_PACING_OPTIONS)]
        scene = (
            f"Shot {i}/{shot_count} — {sprint.product_name}: "
            f"{' '.join(brief_words[:8]) if brief_words else sprint.campaign_objective}"
        )
        motion_prompt = (
            f"{movement} reveal of {sprint.product_name}, "
            f"{color_palette} lighting, targeting {sprint.target_audience}"
        )
        shots.append(
            ShotPlan(
                shot_number=i,
                scene_description=scene,
                motion_prompt=motion_prompt,
                keyframe_guidance=f"Frame {sprint.product_name} prominently; maintain {color_palette} palette.",
                camera_movement=movement,
                pacing=pacing,
                duration_seconds=5,
            )
        )
    return shots


def _build_vos_9shot_plan(sprint: Sprint, color_palette: str) -> list[ShotPlan]:
    """Build the VOS-standard 9-shot plan: 3 blocks × 3 shots (Establish → Engage → Convert)."""
    shots: list[ShotPlan] = []
    shot_number = 1
    for _block_name, pacing, shot_defs in _VOS_SHOT_BLOCKS:
        for role, movement, scene_template, keyframe_template in shot_defs:
            scene = scene_template.format(
                product=sprint.product_name,
                audience=sprint.target_audience,
            )
            keyframe = keyframe_template.format(
                product=sprint.product_name,
                palette=color_palette,
                audience=sprint.target_audience,
            )
            motion_prompt = (
                f"{movement} — {role} of {sprint.product_name}, "
                f"{color_palette} color palette, targeting {sprint.target_audience}"
            )
            shots.append(
                ShotPlan(
                    shot_number=shot_number,
                    scene_description=scene,
                    motion_prompt=motion_prompt,
                    keyframe_guidance=keyframe,
                    camera_movement=movement,
                    pacing=pacing,
                    duration_seconds=4,
                )
            )
            shot_number += 1
    return shots


def _build_negative_prompts(restrictions: dict[str, object]) -> list[str]:
    base = [
        "blurry or out-of-focus frames",
        "watermarks or overlaid text",
        "competitor branding",
        "distorted proportions",
        "low-resolution artifacts",
    ]
    forbidden_elements: object = restrictions.get("forbidden_elements")
    if isinstance(forbidden_elements, list):
        base.extend(str(f) for f in forbidden_elements)
    elif isinstance(forbidden_elements, str) and forbidden_elements:
        base.append(forbidden_elements)
    forbidden_phrases: object = restrictions.get("forbidden_phrases")
    if isinstance(forbidden_phrases, list):
        base.extend(str(f) for f in forbidden_phrases)
    elif isinstance(forbidden_phrases, str) and forbidden_phrases:
        base.append(forbidden_phrases)
    return base


def _build_provider_packs(
    sprint: Sprint,
    data: VideoBlueprintInput,
    shot_plan: list[ShotPlan],
    negative_prompts: list[str],
) -> list[ProviderExecutionPack]:
    master_prompt = shot_plan[0].motion_prompt if shot_plan else sprint.campaign_objective
    neg_fragment = ", ".join(negative_prompts[:3]) if negative_prompts else ""
    packs: list[ProviderExecutionPack] = []

    for provider in data.provider_targets:
        settings = dict(_PROVIDER_BASE_SETTINGS.get(provider, {}))
        settings["prompt_version"] = data.prompt_version
        settings["preset_version"] = data.preset_version

        adapted = master_prompt
        if neg_fragment:
            adapted += f" | Negative: {neg_fragment}"

        packs.append(
            ProviderExecutionPack(
                provider=provider,
                model_recommendation=_PROVIDER_MODELS.get(provider, provider),
                adapted_prompt=adapted,
                settings=settings,
                checklist=_PROVIDER_CHECKLISTS.get(provider, ["Follow provider dashboard steps."]),
            )
        )
    return packs


def _build_manual_checklist(sprint: Sprint, data: VideoBlueprintInput) -> list[str]:
    return [
        f"✓ Review creative intent and confirm alignment with {sprint.campaign_objective}",
        f"✓ Confirm shot plan ({data.shot_count} shots) with creative lead",
        "✓ Validate negative prompt list against brand restrictions",
        "✓ Select provider(s) and prepare execution environment",
        "✓ Execute shots per provider packs — do not deviate from motion prompts",
        "✓ QA each clip: resolution, branding, pacing, no artefacts",
        "✓ Register each approved asset via register_manual_asset",
        "✓ Record performance score after first 48 h of exposure",
    ]


def _build_cost_notes(sprint: Sprint) -> str:
    remaining = sprint.max_spend_usd - sprint.spent_usd
    pct_used = (sprint.spent_usd / sprint.max_spend_usd * 100) if sprint.max_spend_usd else 0
    return (
        f"Budget: ${sprint.max_spend_usd:.2f} approved | "
        f"${sprint.spent_usd:.2f} spent ({pct_used:.0f}%) | "
        f"${remaining:.2f} remaining. "
        "API video generation costs vary by provider and duration — "
        "confirm pricing before executing paid generations."
    )


def _build_risk_notes(sprint: Sprint, brand_kit: BrandKit | None) -> str:
    notes = []
    if sprint.spent_usd >= sprint.max_spend_usd * sprint.alert_threshold_pct:
        notes.append("⚠ Budget alert threshold reached — obtain approval before paid generation.")
    if brand_kit is None:
        notes.append("⚠ No brand kit found — visual consistency not guaranteed.")
    if not notes:
        notes.append("No blocking risks identified.")
    return " ".join(notes)
