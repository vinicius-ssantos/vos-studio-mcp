"""Campaign angle generator service (Issue #49).

Pure composition — no external API calls, no DB, no paid side effects.
"""

from vos_studio_mcp.schemas.campaign_angles import (
    CampaignAngle,
    CampaignAnglesInput,
    CampaignAnglesResponse,
)

_ANGLE_TYPES = [
    "emotional",
    "rational",
    "social_proof",
    "urgency",
    "curiosity",
    "authority",
]

_SHORT_FORMAT_TYPES = {"emotional", "urgency", "curiosity"}
_LONG_FORMAT_TYPES = {"rational", "social_proof", "authority"}


def _format_suggestion(platform: str, angle_type: str) -> str:
    platform_lower = platform.lower()
    if platform_lower == "meta":
        if angle_type in _SHORT_FORMAT_TYPES:
            return "15s Reel"
        return "30s Feed Video"
    if platform_lower == "tiktok":
        return "15-30s TikTok"
    if platform_lower == "youtube":
        if angle_type in _SHORT_FORMAT_TYPES:
            return "15s Pre-roll"
        return "30s Pre-roll"
    if platform_lower == "linkedin":
        return "30s Sponsored Video"
    return "30s Video"


def _build_angle(
    index: int,
    angle_type: str,
    product: str,
    audience: str,
    platform: str,
    objective: str,
) -> CampaignAngle:
    angle_id = f"angle_{index + 1:02d}"
    fmt = _format_suggestion(platform, angle_type)

    if angle_type == "emotional":
        hook = f"What would it feel like to finally solve {product}?"
        primary_message = f"For {audience} who want {objective}, {product} delivers emotional value."
        cta = "See how"
        title = f"Feel the difference with {product}"
    elif angle_type == "rational":
        hook = f"Here's why {product} outperforms the alternatives."
        primary_message = f"Data-driven results for {audience}. {product} is the logical choice."
        cta = "Learn more"
        title = f"The rational case for {product}"
    elif angle_type == "social_proof":
        hook = f"Thousands of {audience} already trust {product}."
        primary_message = f"Join the community and discover what {product} can do for you."
        cta = "Join now"
        title = f"{product}: trusted by {audience}"
    elif angle_type == "urgency":
        hook = f"Limited time — {product} is transforming {audience}."
        primary_message = "Don't miss out. Act before your competitors do."
        cta = "Get started"
        title = f"Act now: {product} for {audience}"
    elif angle_type == "curiosity":
        hook = f"Most {audience} don't know this about {product}..."
        primary_message = f"Surprising insights that make {product} the standout choice."
        cta = "Find out"
        title = f"The secret behind {product}"
    else:  # authority
        hook = f"{product}: The industry standard for {audience}."
        primary_message = f"Trusted by experts. Proven results. The authority choice for {audience}."
        cta = "Trust the experts"
        title = f"{product}: the authority choice"

    return CampaignAngle(
        angle_id=angle_id,
        title=title,
        hook=hook,
        angle_type=angle_type,
        primary_message=primary_message,
        cta=cta,
        format_suggestion=fmt,
    )


def _is_covered_by_existing(angle_type: str, existing_angles: list[str]) -> bool:
    """Return True if the angle type word appears in any existing angle text."""
    return any(angle_type in existing.lower() for existing in existing_angles)


def _hook_matches_existing(hook: str, existing_angles: list[str]) -> bool:
    """Return True if the hook is a substring of (or contains) any existing angle."""
    hook_lower = hook.lower()
    for existing in existing_angles:
        existing_lower = existing.lower()
        if hook_lower in existing_lower or existing_lower in hook_lower:
            return True
    return False


async def generate_campaign_angles(
    client_id: str,
    data: CampaignAnglesInput,
) -> CampaignAnglesResponse:
    """Generate n_angles diverse campaign angles using template-based composition."""
    # Build an ordered list of angle types to use, skipping covered ones first
    available_types = [t for t in _ANGLE_TYPES if not _is_covered_by_existing(t, data.existing_angles)]

    # If we exhausted unique new types, fall back to all types (cycling)
    if not available_types:
        available_types = list(_ANGLE_TYPES)

    angles: list[CampaignAngle] = []
    type_index = 0

    while len(angles) < data.n_angles:
        # Cycle through available types
        angle_type = available_types[type_index % len(available_types)]
        type_index += 1

        candidate = _build_angle(
            index=len(angles),
            angle_type=angle_type,
            product=data.product_description,
            audience=data.target_audience,
            platform=data.platform,
            objective=data.campaign_objective,
        )

        # Skip if hook closely matches an existing angle
        if _hook_matches_existing(candidate.hook, data.existing_angles):
            # Avoid infinite loop: if we've cycled through all types, stop
            if type_index >= len(available_types) * data.n_angles:
                break
            continue

        angles.append(candidate)

    unique_types = {a.angle_type for a in angles}
    diversity_score = min(len(unique_types) / max(len(angles), 1), 1.0)

    summary = (
        f"Generated {len(angles)} campaign angles for {data.platform.upper()}. "
        f"Diversity score: {diversity_score:.0%}."
    )

    return CampaignAnglesResponse(
        status="ok",
        client_id=client_id,
        product_description=data.product_description,
        target_audience=data.target_audience,
        platform=data.platform,
        angles=angles,
        diversity_score=diversity_score,
        summary=summary,
        next_action="prepare_creative_brief",
    )
