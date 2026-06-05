"""Celery task — poll provider job status (ADR-0028, ADR-0044, Issue #6 item C)."""

import asyncio
import logging
from typing import Any

from celery.exceptions import MaxRetriesExceededError

from vos_studio_mcp.services.audit_service import AuditAction, AuditResult, emit_audit_event
from vos_studio_mcp.services.budget_guard import record_actual_cost, release_reserved_budget
from vos_studio_mcp.services.database import (
    get_asset_notification_context,
    get_asset_with_client,
    get_session,
)
from vos_studio_mcp.services.providers import get_adapter
from vos_studio_mcp.tasks.celery_app import celery_app
from vos_studio_mcp.tasks.notify_webhook import enqueue_webhook_failed
from vos_studio_mcp.tasks.upload_video import upload_video_to_storage

log = logging.getLogger(__name__)

_MAX_RETRIES = 60
_POLL_INTERVAL = 30

_RETRY_STATUSES = {"queued", "running"}
_TERMINAL_STATUSES = {"completed", "failed", "timed_out"}


@celery_app.task(bind=True, max_retries=_MAX_RETRIES, name="tasks.poll_video_job")  # type: ignore[untyped-decorator]
def poll_video_job(self: Any, asset_id: str) -> None:
    """Poll Higgsfield for job completion and update the asset record.

    Re-schedules itself every 30 s while the job is still running.
    Dispatches upload_video_to_storage when the job completes.
    Marks the asset as failed after 60 retries (~30 min).
    """
    outcome = asyncio.run(_check_and_update(asset_id))
    if outcome == "retry":
        try:
            raise self.retry(countdown=_POLL_INTERVAL)
        except MaxRetriesExceededError:
            asyncio.run(_mark_status(asset_id, "failed"))
            log.error("poll_video_job.timed_out", extra={"asset_id": asset_id})


async def _check_and_update(asset_id: str) -> str:
    async with get_session() as session:
        asset, _client_id = await get_asset_with_client(session, asset_id)
        if asset is None or not asset.provider_job_id:
            log.warning("poll_video_job.asset_not_found", extra={"asset_id": asset_id})
            return "done"

        if asset.generation_status in _TERMINAL_STATUSES:
            return "done"

        adapter = get_adapter(asset.provider or "higgsfield")
        try:
            job_status = await adapter.check_job_status(asset.provider_job_id)
        except Exception as exc:
            log.warning(
                "poll_video_job.check_error",
                extra={"asset_id": asset_id, "error": str(exc)},
            )
            return "retry"

        if job_status.status in _RETRY_STATUSES:
            return "retry"

        provider = asset.provider or "higgsfield"

        if job_status.status == "completed":
            asset.generation_status = "completed"
            usage_event_id = asset.provider_usage_event_id
            if job_status.media_url:
                # Mark upload as pending; the task will write storage_url + 'stored'
                asset.storage_status = "pending"
            await session.commit()
            log.info(
                "generation.completed",
                extra={"asset_id": asset_id, "job_id": asset.provider_job_id, "provider": provider},
            )
            if job_status.media_url:
                upload_video_to_storage.delay(asset_id, job_status.media_url)
            # Fix #64: Reconcile the budget ledger by recording that the
            # generation completed. Record 0.0 as the actual cost (meaning
            # "completed; actual matches estimate"). record_actual_cost is
            # best-effort and swallows any errors so it never blocks the
            # primary workflow.
            if usage_event_id is not None:
                await record_actual_cost(str(usage_event_id), 0.0)
            await emit_audit_event(
                action=AuditAction.POLL_JOB_COMPLETED,
                entity_type="asset",
                entity_id=asset_id,
                provider=provider,
                result=AuditResult.SUCCESS,
            )
        else:
            provider_job_id = asset.provider_job_id
            asset.generation_status = "failed"
            # Failed generation produced no deliverable — return the reserved
            # estimate to the sprint budget (ADR-0039 #5). Atomic with the
            # status transition; idempotent.
            released = await release_reserved_budget(session, asset)
            await session.commit()
            if released:
                log.info(
                    "generation.budget_released",
                    extra={"asset_id": asset_id, "released_usd": released},
                )
            await emit_audit_event(
                action=AuditAction.POLL_JOB_FAILED,
                entity_type="asset",
                entity_id=asset_id,
                provider=provider,
                result=AuditResult.FAILED,
                failure_reason=job_status.error,
            )
            log.error(
                "generation.failed",
                extra={
                    "asset_id": asset_id,
                    "job_id": provider_job_id,
                    "provider": provider,
                    "error_code": "provider_error",
                    "error": job_status.error,
                },
            )
            # Enqueue a durable Celery webhook notification (best-effort, retryable)
            sprint_id, client_id, webhook_url = await get_asset_notification_context(asset_id)
            if webhook_url and sprint_id and client_id:
                enqueue_webhook_failed(
                    asset_id=asset_id,
                    sprint_id=sprint_id,
                    client_id=client_id,
                    webhook_url=webhook_url,
                    provider_job_id=provider_job_id,
                    event="asset.failed",
                )

    return "done"


async def _mark_status(asset_id: str, status: str) -> None:
    async with get_session() as session:
        asset, _ = await get_asset_with_client(session, asset_id)
        if asset is not None:
            asset.generation_status = status
            # On timeout-driven failure, release the reserved estimate too
            # (ADR-0039 #5). Idempotent via release_reserved_budget.
            if status == "failed":
                await release_reserved_budget(session, asset)
            await session.commit()
