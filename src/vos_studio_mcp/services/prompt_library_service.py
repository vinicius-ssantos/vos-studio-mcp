"""Prompt library service — promote and query cross-client prompt templates (ADR-0029)."""

import datetime
import logging
import uuid

from sqlalchemy import select

from db.models import Asset, PromptTemplate, Sprint
from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.schemas.prompt_template import (
    PromoteToLibraryInput,
    PromoteToLibraryResponse,
    PromptTemplateSuggestion,
    SearchLibraryInput,
    SearchLibraryResponse,
    SearchLibraryResult,
)
from vos_studio_mcp.services.audit_service import AuditAction, AuditResult, emit_audit_event
from vos_studio_mcp.services.database import get_session

log = logging.getLogger(__name__)

_ANONYMIZATION_CHECKLIST = [
    "Replace brand name with {{brand_name}}",
    "Replace product name with {{product_name}}",
    "Remove client-specific visual references (logo colors, mascots, etc.)",
    "Replace specific location or market references with {{market}}",
    "Verify no personally identifiable information (PII) remains",
    "Replace competitor mentions with {{competitor}} or remove entirely",
    "Confirm the template is useful without brand-specific context",
]


async def promote_to_library(
    data: PromoteToLibraryInput, operator_email: str
) -> PromoteToLibraryResponse:
    if not data.confirmed:
        return PromoteToLibraryResponse(
            status="preview",
            template_id=None,
            name=data.name,
            performance_tier="experimental",
            summary=(
                "Review the anonymization checklist before promoting this prompt to the library. "
                "Set confirmed=True once all brand-specific content has been replaced with placeholders."
            ),
            next_action="promote_to_library",
            anonymization_checklist=_ANONYMIZATION_CHECKLIST,
        )

    async with get_session() as session:
        sprint = await session.get(Sprint, uuid.UUID(data.sprint_id))
        if sprint is None:
            raise VosError(ErrorCode.NOT_FOUND, f"Sprint {data.sprint_id} not found")

        # Guard: require at least one QA-approved asset in the sprint before promoting
        # a prompt template — ensures only proven prompts enter the library.
        approved_count_result = await session.execute(
            select(Asset).where(
                Asset.sprint_id == uuid.UUID(data.sprint_id),
                Asset.qa_status == "approved",
            )
        )
        if not approved_count_result.scalars().first():
            raise VosError(
                ErrorCode.VALIDATION_ERROR,
                "Cannot promote to library: sprint has no QA-approved assets. "
                "Run review_asset_quality on at least one asset and achieve an "
                "'approved' outcome before promoting this prompt template.",
            )

        # Verify the prompt_template contains at least one placeholder
        if "{{" not in data.prompt_template:
            raise VosError(
                ErrorCode.VALIDATION_ERROR,
                "prompt_template must contain at least one {{placeholder}} — "
                "brand-specific content must be anonymized before promoting to the library.",
            )

        template = PromptTemplate(
            id=uuid.uuid4(),
            name=data.name,
            description=data.description,
            industry=data.industry,
            format=data.format,
            objective=data.objective,
            platform=data.platform,
            asset_stage=data.asset_stage,
            prompt_template=data.prompt_template,
            negative_prompt_template=data.negative_prompt_template,
            preset_recommendations=data.preset_recommendations,
            usage_count=0,
            performance_tier="experimental",
            derived_from_sprint_ids=[data.sprint_id],
            contributed_by=operator_email,
            approved_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(template)
        await session.commit()
        await session.refresh(template)

    await emit_audit_event(
        action=AuditAction.PROMPT_PROMOTED,
        entity_type="prompt_template",
        entity_id=str(template.id),
        result=AuditResult.SUCCESS,
    )
    log.info(
        "prompt_library.promoted",
        extra={
            "template_id": str(template.id),
            "template_name": template.name,
            "sprint_id": data.sprint_id,
            "contributed_by": operator_email,
        },
    )

    return PromoteToLibraryResponse(
        status="created",
        template_id=str(template.id),
        name=template.name,
        performance_tier=template.performance_tier,
        summary=(
            f"Prompt template '{template.name}' added to the agency library as experimental. "
            "It will be surfaced as a suggestion in matching future sprints."
        ),
        next_action="create_creative_sprint",
        anonymization_checklist=_ANONYMIZATION_CHECKLIST,
    )


async def get_library_suggestions(
    industry: list[str],
    format: list[str],
    objective: list[str],
    platform: list[str],
) -> list[PromptTemplateSuggestion]:
    async with get_session() as session:
        result = await session.scalars(
            select(PromptTemplate)
            .where(PromptTemplate.performance_tier != "deprecated")
            .order_by(PromptTemplate.usage_count.desc())
            .limit(10)
        )
        templates = list(result)

    def _matches(t: PromptTemplate) -> bool:
        t_industry: list[str] = t.industry or []
        t_format: list[str] = t.format or []
        t_objective: list[str] = t.objective or []
        t_platform: list[str] = t.platform or []
        return bool(
            (not industry or set(industry) & set(t_industry))
            and (not format or set(format) & set(t_format))
            and (not objective or set(objective) & set(t_objective))
            and (not platform or set(platform) & set(t_platform))
        )

    return [
        PromptTemplateSuggestion(
            template_id=str(t.id),
            name=t.name,
            performance_tier=t.performance_tier,
            avg_ctr=t.avg_ctr,
            prompt_preview=t.prompt_template[:200],
        )
        for t in templates
        if _matches(t)
    ]


# Performance-tier ordering for min_tier filtering.
_TIER_RANK: dict[str, int] = {
    "experimental": 0,
    "tested": 1,
    "top_performer": 2,
}


async def search_library(data: SearchLibraryInput) -> SearchLibraryResponse:
    """Full-text + faceted search over the cross-client prompt library.

    Keyword search (data.query) matches against name, description, and
    prompt_template via case-insensitive substring matching in Python
    (no FTS extension required).  Tag filters (industry, format, objective,
    platform) and min_tier narrow the result set.  Results are ranked by
    performance tier (top_performer first), then by usage_count descending.
    """
    async with get_session() as session:
        stmt = (
            select(PromptTemplate)
            .where(PromptTemplate.performance_tier != "deprecated")
            .order_by(PromptTemplate.usage_count.desc())
            .limit(data.limit * 10)  # over-fetch so we can filter in Python
        )
        raw = list(await session.scalars(stmt))

    def _tier_rank(tier: str) -> int:
        return _TIER_RANK.get(tier, -1)

    min_rank = _tier_rank(data.min_tier) if data.min_tier else -1

    def _matches(t: PromptTemplate) -> bool:
        # keyword search across name + description + template text
        if data.query:
            needle = data.query.lower()
            haystack = " ".join(
                filter(None, [t.name, getattr(t, "description", None), t.prompt_template])
            ).lower()
            if needle not in haystack:
                return False

        # tag filters — any overlap is sufficient (OR within a facet, AND between facets)
        t_industry: list[str] = t.industry or []
        t_format: list[str] = t.format or []
        t_objective: list[str] = t.objective or []
        t_platform: list[str] = t.platform or []
        t_asset_stage: list[str] = getattr(t, "asset_stage", None) or []
        if data.industry and not set(data.industry) & set(t_industry):
            return False
        if data.format and not set(data.format) & set(t_format):
            return False
        if data.objective and not set(data.objective) & set(t_objective):
            return False
        if data.platform and not set(data.platform) & set(t_platform):
            return False
        # asset_stage filter: templates with no stage tag are stage-agnostic and always match
        if data.asset_stage and t_asset_stage and not set(data.asset_stage) & set(t_asset_stage):
            return False

        # minimum performance tier
        return not (min_rank >= 0 and _tier_rank(t.performance_tier) < min_rank)

    matched = [t for t in raw if _matches(t)]
    # Sort: top tier first, then highest usage_count
    matched.sort(key=lambda t: (_tier_rank(t.performance_tier), t.usage_count or 0), reverse=True)
    matched = matched[: data.limit]

    results = [
        SearchLibraryResult(
            template_id=str(t.id),
            name=t.name,
            description=getattr(t, "description", "") or "",
            performance_tier=t.performance_tier,
            avg_ctr=t.avg_ctr,
            usage_count=t.usage_count or 0,
            industry=t.industry or [],
            format=t.format or [],
            objective=t.objective or [],
            platform=t.platform or [],
            asset_stage=getattr(t, "asset_stage", None) or [],
            prompt_preview=t.prompt_template[:300],
        )
        for t in matched
    ]

    next_action = "prepare_video_blueprint" if results else "promote_to_library"
    return SearchLibraryResponse(
        status="ok",
        total=len(results),
        results=results,
        next_action=next_action,
    )
