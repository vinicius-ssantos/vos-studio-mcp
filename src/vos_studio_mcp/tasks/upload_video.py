"""Celery task — download from provider CDN and upload to R2 (Issue #6 item D)."""

import asyncio
import logging
from typing import Any

from vos_studio_mcp.services import storage
from vos_studio_mcp.services.audit_service import AuditAction, AuditResult, emit_audit_event
from vos_studio_mcp.services.database import (
    get_asset_notification_context,
    get_asset_with_client,
    get_session,
)
from vos_studio_mcp.tasks.celery_app import celery_app
from vos_studio_mcp.tasks.notify_webhook import enqueue_webhook_completed, enqueue_webhook_failed

log = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60, name="tasks.upload_video_to_storage")  # type: ignore[untyped-decorator]
def upload_video_to_storage(self: Any, asset_id: str, media_url: str) -> None:
    """Download the generated video from the provider CDN and upload to R2.

    On success: updates asset.storage_url and asset.storage_status = 'stored'.
    On unrecoverable failure: marks asset.storage_status = 'failed' — the
    generation_status is deliberately left unchanged because the provider job
    did succeed; only the upload step failed (ADR-0031).
    """
    try:
        client_id = asyncio.run(_get_client_id(asset_id))
        if not client_id:
            log.warning("upload_video_to_storage.asset_not_found", extra={"asset_id": asset_id})
            return

        data = storage.download_video(media_url)
        public_url = storage.upload_video(data, asset_id, client_id)
        asyncio.run(_update_storage_url(asset_id, public_url))
        asyncio.run(emit_audit_event(
            action=AuditAction.UPLOAD_COMPLETED,
            entity_type="asset",
            entity_id=asset_id,
            actor=client_id,
            result=AuditResult.SUCCESS,
        ))
        log.info("upload_video_to_storage.done", extra={"asset_id": asset_id})
        _notify_completed(asset_id, public_url)

    except Exception as exc:
        log.error(
            "upload_video_to_storage.failed",
            extra={"asset_id": asset_id, "error": str(exc)},
        )
        try:
            raise self.retry(exc=exc)
        except Exception:
            asyncio.run(_mark_upload_failed(asset_id))
            asyncio.run(emit_audit_event(
                action=AuditAction.UPLOAD_FAILED,
                entity_type="asset",
                entity_id=asset_id,
                result=AuditResult.FAILED,
                failure_reason=str(exc),
            ))
            _notify_upload_failed(asset_id)


async def _get_client_id(asset_id: str) -> str | None:
    async with get_session() as session:
        _asset, client_id = await get_asset_with_client(session, asset_id)
        return client_id


async def _update_storage_url(asset_id: str, public_url: str) -> None:
    async with get_session() as session:
        asset, _ = await get_asset_with_client(session, asset_id)
        if asset is not None:
            asset.storage_url = public_url
            asset.storage_status = "stored"
            await session.commit()


async def _mark_upload_failed(asset_id: str) -> None:
    async with get_session() as session:
        asset, _ = await get_asset_with_client(session, asset_id)
        if asset is not None:
            asset.storage_status = "failed"
            await session.commit()


def _notify_completed(asset_id: str, storage_url: str) -> None:
    """Fetch webhook context from DB and enqueue a durable Celery webhook delivery.

    Errors are swallowed so that a Celery broker outage does not corrupt a
    successfully-stored upload into a failure (review comment, Issue #33).
    """
    async def _run() -> None:
        sprint_id, client_id, webhook_url = await get_asset_notification_context(asset_id)
        if webhook_url and sprint_id and client_id:
            enqueue_webhook_completed(
                asset_id=asset_id,
                sprint_id=sprint_id,
                client_id=client_id,
                webhook_url=webhook_url,
                storage_url=storage_url,
                provider_job_id=None,  # not available here; kept in DB
            )

    try:
        asyncio.run(_run())
    except Exception as exc:
        log.warning(
            "notify_completed.enqueue_failed",
            extra={"asset_id": asset_id, "error": str(exc)},
        )


def _notify_upload_failed(asset_id: str) -> None:
    """Fetch webhook context from DB and enqueue a durable Celery failure notification.

    Errors are swallowed so that a broker outage does not mask the real failure
    reason that was already recorded (review comment, Issue #33).
    """
    async def _run() -> None:
        sprint_id, client_id, webhook_url = await get_asset_notification_context(asset_id)
        if webhook_url and sprint_id and client_id:
            enqueue_webhook_failed(
                asset_id=asset_id,
                sprint_id=sprint_id,
                client_id=client_id,
                webhook_url=webhook_url,
                provider_job_id=None,
                event="asset.upload_failed",
            )

    try:
        asyncio.run(_run())
    except Exception as exc:
        log.warning(
            "notify_upload_failed.enqueue_failed",
            extra={"asset_id": asset_id, "error": str(exc)},
        )
