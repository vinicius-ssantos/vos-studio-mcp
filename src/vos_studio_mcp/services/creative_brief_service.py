"""Creative brief intake service — pure composition, no external API calls (Issue #48)."""

from vos_studio_mcp.schemas.creative_brief import (
    BriefConstraints,
    CreativeBriefInput,
    CreativeBriefResponse,
    RequiredAsset,
)

_ACTION_VERBS = ("increase", "drive", "generate", "launch", "promote", "grow", "retain")

_PAIN_POINT_KEYWORDS: dict[str, str] = {
    "fast": "time constraints",
    "quick": "time constraints",
    "speed": "time constraints",
    "affordable": "budget pressures",
    "cheap": "budget pressures",
    "cost": "budget pressures",
    "easy": "complexity frustration",
    "simple": "complexity frustration",
    "hassle": "complexity frustration",
}

_PLATFORM_OBJECTIONS: dict[str, list[str]] = {
    "meta": ["Too expensive", "Not relevant to me", "Already have a solution"],
    "tiktok": [
        "Skip-worthy if not immediately engaging",
        "Authenticity concerns",
        "Short attention span",
    ],
    "youtube": ["Can be skipped after 5s", "Trust credibility", "Long-form fatigue"],
    "linkedin": [
        "Too salesy for a professional context",
        "Not relevant to my industry",
        "Already using a competitor",
    ],
}

_DEFAULT_OBJECTIONS = [
    "Price too high",
    "Lack of trust or brand recognition",
    "No immediate need perceived",
]

_PLATFORM_ASSETS: dict[str, list[RequiredAsset]] = {
    "meta": [
        RequiredAsset(asset_type="video", format="9:16", quantity=3, notes="Reels-format"),
        RequiredAsset(asset_type="image", format="1:1", quantity=5, notes="Feed posts"),
    ],
    "tiktok": [
        RequiredAsset(asset_type="video", format="9:16", quantity=5, notes="Native TikTok format"),
    ],
    "youtube": [
        RequiredAsset(asset_type="video", format="16:9", quantity=2, notes="Pre-roll or mid-roll"),
    ],
    "linkedin": [
        RequiredAsset(asset_type="image", format="1.91:1", quantity=3, notes="Sponsored content"),
        RequiredAsset(asset_type="video", format="16:9", quantity=2, notes="Video ads"),
    ],
}

_DEFAULT_ASSETS = [
    RequiredAsset(asset_type="video", format="16:9", quantity=3, notes="Standard format"),
]

_APPROVAL_CHECKLIST = [
    "✓ Campaign objective confirmed with client",
    "✓ Target audience validated",
    "✓ Compliance notes reviewed",
    "✓ Asset formats approved",
    "✓ Budget allocation set",
]


def _extract_campaign_objective(raw_brief: str) -> str:
    """Return the first clause containing an action verb, or a default."""
    brief_lower = raw_brief.lower()
    for verb in _ACTION_VERBS:
        if verb in brief_lower:
            # Find the sentence/clause containing the verb
            for separator in (".", ",", ";", "\n"):
                for clause in raw_brief.split(separator):
                    if verb in clause.lower():
                        return clause.strip()
    return "Brand Awareness"


def _build_offer_and_promise(product_description: str) -> str:
    """Return the first two sentences of the product description."""
    sentences: list[str] = []
    for part in product_description.split("."):
        stripped = part.strip()
        if stripped:
            sentences.append(stripped)
        if len(sentences) == 2:  # noqa: PLR2004
            break
    if not sentences:
        return product_description
    return ". ".join(sentences) + ("." if not product_description.endswith(".") else "")


def _build_target_persona(target_audience: str, raw_brief: str) -> str:
    """Combine target_audience with any 'for' or 'who' clauses in raw_brief."""
    for keyword in ("for ", "who "):
        lower = raw_brief.lower()
        idx = lower.find(keyword)
        if idx != -1:
            # Extract to the next punctuation or end of string
            clause_start = idx
            clause_end = len(raw_brief)
            for sep in (".", ",", ";", "\n"):
                sep_idx = raw_brief.find(sep, idx)
                if sep_idx != -1 and sep_idx < clause_end:
                    clause_end = sep_idx
            extra = raw_brief[clause_start:clause_end].strip()
            return f"{target_audience} — {extra}"
    return target_audience


def _extract_pain_points(raw_brief: str) -> list[str]:
    """Extract pain points from brief keywords; always return at least one."""
    found: list[str] = []
    brief_lower = raw_brief.lower()
    seen_pain_points: set[str] = set()
    for keyword, pain_point in _PAIN_POINT_KEYWORDS.items():
        if keyword in brief_lower and pain_point not in seen_pain_points:
            found.append(pain_point)
            seen_pain_points.add(pain_point)
        if len(found) == 3:  # noqa: PLR2004
            break
    if not found:
        return ["Identified from brief — verify with client"]
    return found


def _get_objections(platform: str) -> list[str]:
    """Return platform-specific or generic objections."""
    return _PLATFORM_OBJECTIONS.get(platform.lower(), _DEFAULT_OBJECTIONS)


def _extract_creative_angles(raw_brief: str, product_description: str, target_audience: str) -> list[str]:
    """Extract 3 creative angles from brief signals or generate generic ones."""
    angles: list[str] = []
    brief_lower = raw_brief.lower()

    if "how" in brief_lower:
        angles.append("How-to / educational angle")
    if "why" in brief_lower:
        angles.append("Reason-why / rational angle")
    if "what makes" in brief_lower:
        angles.append("Differentiation / 'what makes us different' angle")
    if any(word in brief_lower for word in ("feel", "emotion", "love", "joy", "fear", "excit")):
        angles.append("Emotional storytelling angle")
    if any(word in brief_lower for word in ("testimonial", "review", "customer", "user")):
        angles.append("Social proof / testimonial angle")
    if any(word in brief_lower for word in ("direct", "offer", "discount", "save", "deal")):
        angles.append("Direct response / offer angle")

    if len(angles) >= 3:  # noqa: PLR2004
        return angles[:3]

    # Fill up with generic angles based on product/audience
    generics = [
        f"Problem-solution: highlight how {product_description[:40]} solves a real need",
        f"Audience-first: speak directly to {target_audience} pain points",
        "Contrast angle: before vs. after using the product",
    ]
    for generic in generics:
        if generic not in angles:
            angles.append(generic)
        if len(angles) == 3:  # noqa: PLR2004
            break

    return angles


def _get_required_assets(platform: str) -> list[RequiredAsset]:
    return _PLATFORM_ASSETS.get(platform.lower(), _DEFAULT_ASSETS)


def _get_sprint_type(platform: str) -> str:
    return "dashboard_manual" if platform.lower() in ("meta", "tiktok") else "api_credits"


def _get_provider_notes(assets: list[RequiredAsset]) -> str:
    has_video = any(a.asset_type == "video" for a in assets)
    has_image = any(a.asset_type == "image" for a in assets)
    if has_video and has_image:
        return (
            "Higgsfield for image-to-video; Freepik Mystic for text-to-video and text-to-image; "
            "Magnific for upscaling"
        )
    if has_video:
        return "Higgsfield for image-to-video; Freepik Mystic for text-to-video"
    return "Freepik Mystic for text-to-image; Magnific for upscaling"


def _build_missing_information(
    raw_brief: str,
    platform: str,
    constraints: BriefConstraints,
) -> list[str]:
    missing: list[str] = []
    if len(raw_brief) < 50:  # noqa: PLR2004
        missing.append("Brief is very short — request more detail")
    platform_keywords = {
        "meta": ("facebook", "instagram", "reel", "feed", "story", "meta"),
        "tiktok": ("tiktok", "tok", "short video", "viral"),
        "youtube": ("youtube", "pre-roll", "mid-roll", "video ad"),
        "linkedin": ("linkedin", "b2b", "professional", "sponsored"),
    }
    relevant_keywords = platform_keywords.get(platform.lower(), ())
    if relevant_keywords and not any(kw in raw_brief.lower() for kw in relevant_keywords):
        missing.append("No platform context in brief")
    constraints_empty = (
        not constraints.claims_allowed
        and not constraints.claims_forbidden
        and not constraints.forbidden_topics
        and not constraints.brand_voice
        and not constraints.compliance_notes
    )
    if constraints_empty:
        missing.append("No compliance constraints provided")
    return missing


async def prepare_creative_brief(
    client_id: str,
    data: CreativeBriefInput,
) -> CreativeBriefResponse:
    """Parse a raw client brief and produce a structured creative brief.

    Pure composition — no external API calls, no DB, no paid side effects.
    """
    campaign_objective = _extract_campaign_objective(data.raw_brief)
    offer_and_promise = _build_offer_and_promise(data.product_description)
    target_persona = _build_target_persona(data.target_audience, data.raw_brief)
    pain_points = _extract_pain_points(data.raw_brief)
    objections = _get_objections(data.platform)
    creative_angles = _extract_creative_angles(
        data.raw_brief,
        data.product_description,
        data.target_audience,
    )
    required_assets = _get_required_assets(data.platform)
    suggested_sprint_type = _get_sprint_type(data.platform)
    provider_suitability_notes = _get_provider_notes(required_assets)
    missing_information = _build_missing_information(
        data.raw_brief, data.platform, data.constraints
    )
    summary = (
        f"Brief processed for {data.platform.upper()} campaign. "
        f"{len(required_assets)} asset type(s) required. "
        f"Sprint type: {suggested_sprint_type}."
    )

    return CreativeBriefResponse(
        status="ready",
        client_id=client_id,
        campaign_objective=campaign_objective,
        offer_and_promise=offer_and_promise,
        target_persona=target_persona,
        pain_points=pain_points,
        objections=objections,
        creative_angles=creative_angles,
        required_assets=required_assets,
        suggested_sprint_type=suggested_sprint_type,
        provider_suitability_notes=provider_suitability_notes,
        approval_checklist=_APPROVAL_CHECKLIST,
        missing_information=missing_information,
        summary=summary,
        next_action="create_creative_sprint",
    )
