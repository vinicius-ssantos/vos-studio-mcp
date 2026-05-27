"""Celery Beat scheduled tasks (ADR-0021, Issue #28).

Tasks:
- rollup_performance_memory: daily — aggregates PerformanceRecord rows per brand kit
  and writes proven_angles / proven_hooks / failed_approaches to brand_kit.performance_memory
- cleanup_stale_jobs: weekly — removes API-generated assets that failed > 30 days ago
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select

from db.models import Asset, BrandKit, PerformanceRecord
from vos_studio_mcp.services.database import bypass_rls, get_session
from vos_studio_mcp.services.library_maintenance_service import (
    refresh_library_tiers as do_refresh_library_tiers,
)
from vos_studio_mcp.tasks.celery_app import celery_app

log = logging.getLogger(__name__)

_STALE_DAYS = 30
_TOP_N = 10  # max performers to extract per brand kit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_notes(records: list[PerformanceRecord]) -> list[str]:
    """Return non-empty notes from a list of performance records."""
    return [r.notes for r in records if r.notes]


# ---------------------------------------------------------------------------
# rollup_performance_memory
# ---------------------------------------------------------------------------


@celery_app.task(name="tasks.rollup_performance_memory", bind=True, max_retries=3)  # type: ignore[untyped-decorator]
def rollup_performance_memory(self: Any) -> dict[str, int]:
    """Aggregate PerformanceRecord rows and update brand_kit.performance_memory.

    Runs daily via Celery Beat. For each brand kit that has performance records:
    - proven_angles / proven_hooks → notes from 'top_performer' records (top N by CTR)
    - failed_approaches → notes from 'loser' records

    Idempotent: overwrites existing memory on each run.
    """
    try:
        return asyncio.run(_do_rollup())
    except Exception as exc:
        log.error("rollup_performance_memory.failed", extra={"error": str(exc)})
        raise self.retry(exc=exc, countdown=300) from exc


async def _do_rollup() -> dict[str, int]:
    updated = 0
    skipped = 0

    async with get_session() as session:
        await bypass_rls(session)

        # Find distinct brand_kit_ids that have performance records
        result = await session.execute(
            select(PerformanceRecord.brand_kit_id)
            .where(PerformanceRecord.brand_kit_id.is_not(None))
            .distinct()
        )
        brand_kit_ids: list[uuid.UUID] = [row[0] for row in result.all()]

    for bk_id in brand_kit_ids:
        try:
            was_updated = await _rollup_brand_kit(bk_id)
            if was_updated:
                updated += 1
            else:
                skipped += 1
        except Exception as exc:
            log.warning(
                "rollup_performance_memory.brand_kit_failed",
                extra={"brand_kit_id": str(bk_id), "error": str(exc)},
            )
            skipped += 1

    log.info(
        "rollup_performance_memory.done",
        extra={"updated": updated, "skipped": skipped},
    )
    return {"updated": updated, "skipped": skipped}


async def _rollup_brand_kit(brand_kit_id: uuid.UUID) -> bool:
    async with get_session() as session:
        await bypass_rls(session)

        # Top performers ordered by CTR desc
        top_result = await session.execute(
            select(PerformanceRecord)
            .where(
                PerformanceRecord.brand_kit_id == brand_kit_id,
                PerformanceRecord.performance_label == "top_performer",
            )
            .order_by(PerformanceRecord.ctr.desc().nulls_last())
            .limit(_TOP_N)
        )
        top_records = list(top_result.scalars().all())

        # Failed / loser records
        loser_result = await session.execute(
            select(PerformanceRecord)
            .where(
                PerformanceRecord.brand_kit_id == brand_kit_id,
                PerformanceRecord.performance_label == "loser",
            )
            .order_by(PerformanceRecord.recorded_at.desc())
            .limit(_TOP_N)
        )
        loser_records = list(loser_result.scalars().all())

        brand_kit = await session.get(BrandKit, brand_kit_id)
        if brand_kit is None:
            return False

        memory: dict[str, object] = {
            "proven_angles": _extract_notes(top_records),
            "proven_hooks": [
                r.notes for r in top_records
                if r.notes and r.hook_retention_rate and r.hook_retention_rate > 0.5
            ],
            "failed_approaches": _extract_notes(loser_records),
            "last_rollup_at": datetime.now(UTC).isoformat(),
        }
        brand_kit.performance_memory = memory
        await session.commit()

    log.info(
        "rollup_performance_memory.brand_kit_updated",
        extra={
            "brand_kit_id": str(brand_kit_id),
            "top_performers": len(top_records),
            "losers": len(loser_records),
        },
    )
    return True


# ---------------------------------------------------------------------------
# refresh_library_tiers
# ---------------------------------------------------------------------------


@celery_app.task(name="tasks.refresh_library_tiers", bind=True, max_retries=3)  # type: ignore[untyped-decorator]
def refresh_library_tiers(self: Any) -> dict[str, int]:
    """Recalculate avg_ctr, avg_roas, usage_count and performance_tier for all
    non-deprecated prompt templates.

    Runs daily at 03:30 UTC via Celery Beat.  Can also be triggered on-demand
    via the refresh_library_tiers MCP tool.
    """
    try:
        return asyncio.run(do_refresh_library_tiers())
    except Exception as exc:
        log.error("refresh_library_tiers.failed", extra={"error": str(exc)})
        raise self.retry(exc=exc, countdown=300) from exc


# ---------------------------------------------------------------------------
# cleanup_stale_jobs
# ---------------------------------------------------------------------------


@celery_app.task(name="tasks.cleanup_stale_jobs", bind=True, max_retries=3)  # type: ignore[untyped-decorator]
def cleanup_stale_jobs(self: Any) -> dict[str, int]:
    """Delete API-generated assets that failed more than STALE_DAYS days ago.

    Runs weekly via Celery Beat. Only removes assets where:
    - generation_status = 'failed'
    - provider_job_id IS NOT NULL (API-generated, not manual)
    - created_at < NOW() - STALE_DAYS days

    Manual assets and non-failed assets are never touched.
    """
    try:
        return asyncio.run(_do_cleanup())
    except Exception as exc:
        log.error("cleanup_stale_jobs.failed", extra={"error": str(exc)})
        raise self.retry(exc=exc, countdown=600) from exc


async def _do_cleanup() -> dict[str, int]:
    cutoff = datetime.now(UTC) - timedelta(days=_STALE_DAYS)

    async with get_session() as session:
        await bypass_rls(session)

        result = await session.execute(
            delete(Asset)
            .where(
                Asset.generation_status == "failed",
                Asset.provider_job_id.is_not(None),
                Asset.created_at < cutoff,
            )
            .returning(Asset.id)
        )
        deleted_ids = result.fetchall()
        deleted = len(deleted_ids)
        await session.commit()

    log.info("cleanup_stale_jobs.done", extra={"deleted": deleted, "cutoff": cutoff.isoformat()})
    return {"deleted": deleted}
