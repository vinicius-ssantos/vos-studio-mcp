"""VOS Spec Ad Playbook — MCP resources and prompts (Issue #60).

Exposes the VOS methodology as MCP-native knowledge artifacts:
- Resources: static reference documents (playbook, stage templates, provider guide)
- Prompts: parameterised prompt templates for creative workflow steps

All resources and prompts are read-only, stateless, and require no DB access.
"""

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Stage template content
# ---------------------------------------------------------------------------

_STAGE_CONTENT: dict[str, str] = {
    "stage_0": """# VOS Stage 0 — Anchor Image

## Purpose
The anchor image is the single reference frame that locks the visual identity for the
entire campaign.  Every subsequent asset (character sheet, storyboard, video) derives
from this image.

## Requirements
- Single dominant subject (product or talent)
- Brand color palette applied
- Cinematic composition, no text or watermarks
- Resolution: 1080p minimum
- Aspect ratio: 16:9 (or platform-specific)

## Prompt guidance
> [camera movement] of [product], [brand palette] lighting, [tone] composition,
> no text, no watermarks, photorealistic, [style keywords]

## QA criteria
- Product/subject centered and clearly visible
- Brand color palette applied throughout
- No text, watermarks, or competitor branding
- Mobile-legible at 375px width
- No artifacts or distortion

## Next step
Register with asset_stage=stage_0, approved_as_reference=true.
""",
    "stage_a": """# VOS Stage A — Character Sheet

## Purpose
The character sheet captures all approved talent/character reference angles for the
campaign.  It ensures visual consistency across every shot that features the same
subject.

## Requirements
- Front, 3-quarter, and side angles minimum
- Consistent lighting and palette across all angles
- Source: Stage 0 anchor image as visual reference
- No brand violations

## Prompt guidance
> [character] from [angle], consistent with [Stage 0 anchor], [palette] lighting,
> natural expression, [style keywords]

## QA criteria
- Face/talent legible on mobile
- Consistent lighting and palette across all angles
- Natural pose and expression — no generic stock look
- Correct aspect ratio

## Next step
Register each angle with asset_stage=stage_a, source_asset_id pointing to Stage 0 anchor.
""",
    "stage_b": """# VOS Stage B — Storyboard

## Purpose
The storyboard pre-visualises every shot in the shot plan before any video is generated.
One keyframe per shot aligns the team on composition, scale, and camera movement.

## Requirements
- One frame per shot in the blueprint shot plan
- Matches scene description and camera_movement from the plan
- Scale alternation: wide → medium → close-up across the 9-shot sequence

## Prompt guidance
> [camera_movement] — [scene_description], [brand palette] color palette,
> [product] in frame, no text, [style keywords]

## QA criteria
- Each frame matches shot plan scene description
- Camera angle matches blueprint camera_movement
- Scale alternation respected across sequence
- No artifacts; no text (except CTA shot)

## Next step
Register each frame with asset_stage=stage_b, source_asset_id pointing to Stage 0 or A.
""",
    "stage_c": """# VOS Stage C — Video

## Purpose
Stage C is the final video production.  Each shot from the storyboard becomes an
animated clip; the clips are assembled to the delivery specification.

## VOS 9-Shot Structure
| Block | Shots | Pacing | Purpose |
|-------|-------|--------|---------|
| Establish | 1–3 | slow-burn (4–6 s) | Set location, product reveal, detail |
| Engage | 4–6 | mid-pace (2–4 s) | Lifestyle, emotional beat, full scene |
| Convert | 7–9 | energetic (1–2 s) | Social proof, CTA element, brand close |

## Prompt guidance
> [camera_movement] — [role] of [product], [brand palette] color palette,
> targeting [audience] | Negative: [negative_prompts]

## QA criteria
- Each clip duration matches shot plan (±0.5 s)
- Motion direction matches blueprint camera_movement
- Product visible and correctly positioned throughout
- Brand color palette present
- No artifacts, blur, or compression issues at 1080p
- Pacing matches block specification

## Export spec
- Format: MP4 H.264
- Resolution: 1080p minimum
- Duration: matches brief specification

## Next step
Register with asset_stage=stage_c, asset_kind=generated, source_asset_id pointing to Stage B.
""",
    "repair": """# VOS Repair Stage — Corrected Asset Variant

## Purpose
The repair stage produces a corrected version of a rejected or flagged asset.
The goal is minimal, targeted correction — not full re-generation.

## Process
1. Identify the specific QA failure criteria from the review
2. Map the failure to its root cause (wrong motion, palette drift, artifact, etc.)
3. Execute the minimal correction targeting only the identified failure
4. Re-run all previously failing QA checks

## Prompt guidance
Retain the original motion prompt unless the prompt was the root cause.
Change only the parameter(s) responsible for the failure.

## QA criteria
- All previously failing QA criteria now pass
- No new issues introduced by the repair
- Motion/style consistent with the original

## Next step
Register with asset_stage=repair, source_asset_id pointing to the original rejected asset.
Then use review_asset_quality to validate.
""",
    "final": """# VOS Final Stage — Delivery Asset

## Purpose
The final delivery asset is the approved, assembled sprint deliverable.
It represents the complete creative output, ready for campaign distribution.

## Requirements
- All Stage C clips approved and registered
- Final QA pass on the assembled video
- Export matches delivery specification
- No pending QA flags

## Delivery spec
- Format: MP4 H.264
- Resolution: 1080p minimum
- Codec: H.264
- Aspect ratio: as specified in brief
- Total duration: within brief specification

## QA checklist
- Product consistency verified end-to-end
- Label accuracy: all text/on-screen labels correct
- Campaign coherence: narrative arc is clear
- Mobile readability at 375px
- Endcard: CTA legible, brand mark visible, duration correct
- No risky claims or policy violations

## Next step
Register with asset_stage=final, is_final_delivery=true, approved_as_reference=true.
""",
}

_PLAYBOOK_OVERVIEW = """# VOS Spec Ad Playbook — Overview

## The VOS Method

VOS (Video Operating System) is a stage-based creative production method for
performance-optimised short-form video ads.  It turns a brand kit and sprint brief
into a controlled, repeatable production workflow.

## Core Principles

1. **Stage-based production**: Every asset is produced in a defined stage (0 → A → B → C).
   Each stage gates the next.
2. **Visual anchoring**: Stage 0 locks visual identity.  All subsequent assets derive from it.
3. **9-shot structure**: The default video plan has 3 blocks × 3 shots with controlled rhythm.
4. **Asset Lock**: Brand kit includes explicit visual constraints (registers, materials, environments,
   text policy, endcard policy).
5. **Iterative QA**: Every asset passes explicit QA criteria before advancing.
6. **Performance loop**: Top-performing assets feed back into future sprint context.

## Production Stages

| Stage | Name | Output |
|-------|------|--------|
| Stage 0 | Anchor Image | Single visual identity reference frame |
| Stage A | Character Sheet | All approved talent/character reference angles |
| Stage B | Storyboard | One keyframe per shot in the shot plan |
| Stage C | Video | Animated clips assembled to delivery spec |
| Repair | Repair Variant | Corrected version of a rejected asset |
| Final | Delivery Asset | Approved sprint deliverable |

## VOS 9-Shot Structure

```
Block 1 — Establish (shots 1–3, slow-burn 4–6 s)
  Shot 1: Wide establishing shot
  Shot 2: Medium product reveal
  Shot 3: Close-up detail

Block 2 — Engage (shots 4–6, mid-pace 2–4 s)
  Shot 4: Medium lifestyle / context
  Shot 5: Close-up emotional beat
  Shot 6: Wide action / full use

Block 3 — Convert (shots 7–9, energetic 1–2 s)
  Shot 7: Medium social proof / result
  Shot 8: Close-up CTA element
  Shot 9: Wide brand close
```

## MCP Tool Workflow

```
create_client
  → save_brand_kit (with asset_lock)
    → create_creative_sprint
      → prepare_creative_brief
        → generate_campaign_angles
          → prepare_video_blueprint
            → prepare_execution_pack (per stage)
              → register_manual_asset (per asset, with asset_stage)
                → review_asset_quality
                  → record_asset_performance
                    → (next sprint)
```

## Provider Strategy (V1)

- **Higgsfield**: Primary API video generation (Stage C)
- **Freepik**: Image generation (Stage 0, A, B)
- **Magnific**: Image upscaling (Stage 0 anchor enhancement)
- **Manual / Dashboard**: Primary workflow for brand-safe creative execution

## References

- ADR-0010: Sprint as core domain entity
- ADR-0024: Brand kit entity specification
- ADR-0031: Split generation/storage status
- ADR-0037: Asset stage and lineage model
- ADR-0038: Brand kit asset lock (campaign visual system v2)
"""

_PROVIDER_GUIDE = """# VOS Provider Guide

## Higgsfield (API Video Generation)

**Role**: Primary video generation for Stage C.

**Model**: Higgsfield Animate v1

**Settings**:
- aspect_ratio: 16:9
- duration_seconds: 5 (Stage C shots)
- resolution: 720p (preview) / 1080p (delivery)

**Workflow**:
1. Upload Stage 0 anchor image as reference
2. Paste motion prompt from blueprint shot plan
3. Set duration and resolution
4. Review preview frame before confirming generation
5. Download MP4 and register as asset_stage=stage_c

**Circuit breaker**: Automatically trips after 5 consecutive failures.
Use reset_circuit_breaker(provider="higgsfield") to manually reset.

---

## Freepik (Image Generation)

**Role**: Image generation for Stage 0, A, B assets.

**Model**: Freepik Mystic v2

**Settings**:
- style: cinematic
- color_grading: natural
- resolution: 1080p

**Workflow**:
1. Select Mystic model and cinematic style
2. Paste adapted prompt from execution pack
3. Adjust color grading slider to match brand palette
4. Verify style consistency with brand kit
5. Export at 1080p and register asset

---

## Magnific (Image Upscaling)

**Role**: Upscaling and motion enhancement for Stage 0 anchor images.

**Model**: Magnific Upscale+Motion

**Settings**:
- scale_factor: 2
- creativity: 0.5
- resemblance: 0.8

**Workflow**:
1. Upload source frame
2. Set scale factor 2x and sliders
3. Apply motion effect with pacing from shot plan
4. Download enhanced clip and register as asset_kind=upscaled

---

## Manual / Dashboard

**Role**: Primary workflow for all stages.

**Use when**:
- Provider API is unavailable (circuit breaker open)
- Budget requires human approval
- Stage 0/A/B image work with a human photographer or designer

**Workflow**:
1. Use prepare_execution_pack to get stage-specific operator steps
2. Execute per the operator_steps in the pack
3. QA against qa_criteria in the pack
4. Register via register_manual_asset with asset_stage and asset_kind
"""


# ---------------------------------------------------------------------------
# Module-level prompt functions (testable directly)
# ---------------------------------------------------------------------------


def vos_creative_brief(
    brand_name: str,
    product: str,
    target_audience: str,
    campaign_objective: str,
    platform: str = "Instagram Reels, TikTok",
) -> str:
    """VOS creative brief template parameterised for a specific campaign."""
    return f"""# Creative Brief — {brand_name}

## Campaign Overview
- **Brand**: {brand_name}
- **Product**: {product}
- **Target Audience**: {target_audience}
- **Campaign Objective**: {campaign_objective}
- **Platform**: {platform}

## Creative Direction
Produce a performance-optimised video ad using the VOS 9-shot structure.

The creative must:
1. Open with a strong visual hook (Stage 0 anchor image)
2. Follow the Establish → Engage → Convert arc across 9 shots
3. Feature {product} prominently in every shot
4. Speak directly to {target_audience}
5. Deliver a clear CTA in shots 8–9

## Tone and Style
- Authentic, not polished-generic
- Product-forward: {product} is always the hero
- Optimised for {platform}: vertical/square format, mobile-first composition

## Constraints
- No competitor branding
- No watermarks or overlaid text (except CTA in shot 8)
- No distorted proportions or low-resolution artifacts
- Follow brand restrictions in the brand kit

## Suggested Next Steps
1. Run `save_brand_kit` with full identity, visual, restrictions, and asset_lock
2. Run `create_creative_sprint` with this brief
3. Run `prepare_creative_brief` to get the structured brief output
4. Run `prepare_video_blueprint` to get the 9-shot plan
5. Run `prepare_execution_pack` for each stage (stage_0 → stage_a → stage_b → stage_c)
"""


def vos_shot_direction(
    shot_number: int,
    role: str,
    camera_movement: str,
    product: str,
    target_audience: str,
    color_palette: str = "brand palette",
    duration_seconds: int = 5,
) -> str:
    """Direction template for a single shot in the VOS 9-shot structure."""
    return f"""# Shot {shot_number} Direction

## Role
{role}

## Camera Movement
{camera_movement}

## Motion Prompt
{camera_movement} — {role} of {product}, {color_palette} color palette,
targeting {target_audience}

## Keyframe Guidance
Frame {product} prominently with {camera_movement.lower()} motion.
Maintain {color_palette} palette throughout the {duration_seconds}s clip.
Subject should be clearly visible and correctly positioned by frame 1.

## Duration
{duration_seconds} seconds

## QA Checklist
- [ ] Duration matches specification (±0.5 s)
- [ ] Motion direction matches "{camera_movement}"
- [ ] {product} visible and correctly positioned
- [ ] {color_palette} palette present
- [ ] No artifacts, blur, or compression issues
- [ ] No watermarks, competitor branding, or text (unless CTA shot)

## After Generation
Register with `register_manual_asset` including:
- asset_stage: stage_c
- asset_kind: generated
- notes: "Shot {shot_number} — {role}"
"""


# ---------------------------------------------------------------------------
# Registration function
# ---------------------------------------------------------------------------


def register_resources_and_prompts(mcp: FastMCP) -> None:
    """Register MCP resources and prompts for VOS knowledge artifacts."""

    # ------------------------------------------------------------------
    # Resources
    # ------------------------------------------------------------------

    @mcp.resource(
        "vos://playbook",
        name="vos_playbook",
        description="VOS Spec Ad Playbook — the complete methodology overview",
        mime_type="text/markdown",
    )
    def _vos_playbook() -> str:
        """VOS Spec Ad Playbook overview: method, 9-shot structure, stages, and tool workflow."""
        return _PLAYBOOK_OVERVIEW

    @mcp.resource(
        "vos://stage-templates/stage_0",
        name="vos_stage_0_template",
        description="VOS Stage 0 — Anchor Image template",
        mime_type="text/markdown",
    )
    def _stage_0_template() -> str:
        return _STAGE_CONTENT["stage_0"]

    @mcp.resource(
        "vos://stage-templates/stage_a",
        name="vos_stage_a_template",
        description="VOS Stage A — Character Sheet template",
        mime_type="text/markdown",
    )
    def _stage_a_template() -> str:
        return _STAGE_CONTENT["stage_a"]

    @mcp.resource(
        "vos://stage-templates/stage_b",
        name="vos_stage_b_template",
        description="VOS Stage B — Storyboard template",
        mime_type="text/markdown",
    )
    def _stage_b_template() -> str:
        return _STAGE_CONTENT["stage_b"]

    @mcp.resource(
        "vos://stage-templates/stage_c",
        name="vos_stage_c_template",
        description="VOS Stage C — Video production template",
        mime_type="text/markdown",
    )
    def _stage_c_template() -> str:
        return _STAGE_CONTENT["stage_c"]

    @mcp.resource(
        "vos://stage-templates/repair",
        name="vos_repair_template",
        description="VOS Repair Stage — corrected asset variant template",
        mime_type="text/markdown",
    )
    def _repair_template() -> str:
        return _STAGE_CONTENT["repair"]

    @mcp.resource(
        "vos://stage-templates/final",
        name="vos_final_template",
        description="VOS Final Stage — delivery asset template",
        mime_type="text/markdown",
    )
    def _final_template() -> str:
        return _STAGE_CONTENT["final"]

    @mcp.resource(
        "vos://providers",
        name="vos_provider_guide",
        description="VOS Provider Guide — Higgsfield, Freepik, Magnific, and Manual",
        mime_type="text/markdown",
    )
    def _provider_guide() -> str:
        return _PROVIDER_GUIDE

    # ------------------------------------------------------------------
    # Prompts — delegate to module-level functions
    # ------------------------------------------------------------------

    @mcp.prompt(
        name="vos_creative_brief",
        description=(
            "Generate a structured VOS creative brief for a new sprint. "
            "Provide brand name, product, target audience, campaign objective, "
            "and platform for a customised brief."
        ),
    )
    def _vos_creative_brief(
        brand_name: str,
        product: str,
        target_audience: str,
        campaign_objective: str,
        platform: str = "Instagram Reels, TikTok",
    ) -> str:
        return vos_creative_brief(brand_name, product, target_audience, campaign_objective, platform)

    @mcp.prompt(
        name="vos_shot_direction",
        description=(
            "Generate detailed direction for a single VOS shot. "
            "Provide shot number, role, camera movement, product, audience, and palette."
        ),
    )
    def _vos_shot_direction(
        shot_number: int,
        role: str,
        camera_movement: str,
        product: str,
        target_audience: str,
        color_palette: str = "brand palette",
        duration_seconds: int = 5,
    ) -> str:
        return vos_shot_direction(
            shot_number, role, camera_movement, product, target_audience,
            color_palette, duration_seconds,
        )
