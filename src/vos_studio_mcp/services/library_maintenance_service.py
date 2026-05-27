"""Prompt library maintenance — performance refresh and auto-tier promotion (ADR-0029).

Aggregates PerformanceRecord data from sprints linked via
PromptTemplate.derived_from_sprint_ids and applies tier-promotion rules:

  top_performer : usage_count >= 10  AND  avg_ctr >= 0.05
  tested        : usage_count >= 5   AND  avg_ctr >= 0.03
  experimental  : below all thresholds (default / fallback)

The rules are intentionally conservative to avoid premature promotion.
Runs automatically via Celery Beat (daily at 03:30 UTC) and can also be
triggered on-demand via the refresh_library_tiers MCP tool.
"""

import logging
import uuid
from collections import defaultdict

from sqlalchemy import select

from db.models import PerformanceRecord, PromptTemplate
from vos_studio_mcp.services.database import bypass_rls, get_session

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tier thresholds  (ordered: highest tier first)
# ---------------------------------------------------------------------------

_TIER_THRESHOLDS: list[tuple[int, float, str]] = [
    (10, 0.05, "top_performer"),
    (5, 0.03, "tested"),
]


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------


async def refresh_library_tiers() -> dict[str, int]:
    """Recalculate avg_ctr, avg_roas, usage_count and performance_tier for all
    non-deprecated prompt templates.

    Returns a dict with "updated" (total templates processed) and "promoted"
    (number whose performance_tier changed).
    """
    async with get_session() as session:
        await bypass_rls(session)

        # ── 1. Load all non-deprecated templates ──────────────────────────
        templates_result = await session.scalars(
            select(PromptTemplate).where(PromptTemplate.performance_tier != "deprecated")
        )
        templates = list(templates_result)

        if not templates:
            return {"updated": 0, "promoted": 0}

        # ── 2. Collect every sprint ID referenced across all templates ─────
        all_sprint_ids: set[uuid.UUID] = set()
        for t in templates:
            for sid in (t.derived_from_sprint_ids or []):
                parsed = _parse_uuid(sid)
                if parsed is not None:
                    all_sprint_ids.add(parsed)

        # ── 3. Bulk-fetch PerformanceRecord rows for those sprints ─────────
        records_by_sprint: dict[uuid.UUID, list[PerformanceRecord]] = defaultdict(list)
        if all_sprint_ids:
            records_result = await session.scalars(
                select(PerformanceRecord).where(
                    PerformanceRecord.sprint_id.in_(all_sprint_ids)
                )
            )
            for rec in records_result:
                records_by_sprint[rec.sprint_id].append(rec)

        # ── 4. Recalculate stats and tier per template ─────────────────────
        updated = 0
        promoted = 0

        for template in templates:
            sprint_ids = [
                _parse_uuid(sid)
                for sid in (template.derived_from_sprint_ids or [])
            ]
            t_records: list[PerformanceRecord] = []
            for sid in sprint_ids:
                if sid is not None:
                    t_records.extend(records_by_sprint.get(sid, []))

            new_avg_ctr = _avg([r.ctr for r in t_records if r.ctr is not None])
            new_avg_roas = _avg([r.roas for r in t_records if r.roas is not None])
            new_usage_count = len(t_records)
            new_tier = _calculate_tier(new_usage_count, new_avg_ctr)
            old_tier = template.performance_tier

            template.avg_ctr = new_avg_ctr
            template.avg_roas = new_avg_roas
            template.usage_count = new_usage_count
            template.performance_tier = new_tier

            if new_tier != old_tier:
                promoted += 1
                log.info(
                    "library_maintenance.tier_changed",
                    extra={
                        "template_id": str(template.id),
                        "old_tier": old_tier,
                        "new_tier": new_tier,
                        "usage_count": new_usage_count,
                        "avg_ctr": new_avg_ctr,
                    },
                )

            updated += 1

        await session.commit()

    log.info(
        "library_maintenance.refresh_done",
        extra={"updated": updated, "promoted": promoted},
    )
    return {"updated": updated, "promoted": promoted}


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _calculate_tier(usage_count: int, avg_ctr: float | None) -> str:
    """Return the highest tier the template qualifies for."""
    if avg_ctr is not None:
        for min_count, min_ctr, tier in _TIER_THRESHOLDS:
            if usage_count >= min_count and avg_ctr >= min_ctr:
                return tier
    return "experimental"


def _avg(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _parse_uuid(value: object) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError):
        return None
