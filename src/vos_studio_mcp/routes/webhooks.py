"""Webhook receiver for provider callbacks (ADR-0028)."""

import json
import logging
from typing import Any, Literal

from fastapi import APIRouter, Request, Response
from sqlalchemy import text

from db.models import Asset
from vos_studio_mcp.services.audit_service import AuditAction, AuditResult, emit_audit_event
from vos_studio_mcp.services.database import bypass_rls, get_session, set_tenant_context
from vos_studio_mcp.services.providers import get_adapter
from vos_studio_mcp.tasks.upload_image import upload_image_to_storage
from vos_studio_mcp.tasks.upload_video import upload_video_to_storage

log = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks")

# Provider media type mapping — determines which upload task to use
_PROVIDER_MEDIA_TYPE: dict[str, str] = {
    "higgsfield": "video",
    "freepik": "image",
    "magnific": "image",
}

_STATUS_MAP: dict[str, Literal["pending", "processing", "completed", "failed"]] = {
    # uppercase variants (Higgsfield, Freepik)
    "QUEUED": "pending",
    "PENDING": "pending",
    "PROCESSING": "processing",
    "COMPLETED": "completed",
    "FAILED": "failed",
    "ERROR": "failed",
    # lowercase variants (Magnific)
    "queued": "pending",
    "pending": "pending",
    "processing": "processing",
    "completed": "completed",
    "failed": "failed",
    "error": "failed",
}


async def _process_provider_webhook(
    provider: str,
    job_id: str,
    raw_status: str,
    media_url: str | None,
) -> dict[str, bool]:
    """Shared webhook processing logic: update asset status and enqueue upload.

    Looks up the asset by provider_job_id bypassing RLS, then re-enables RLS
    for the tenant-scoped update. Unknown job IDs are silently ignored.
    """
    if not job_id:
        log.warning(f"{provider}_webhook.missing_job_id")
        return {"received": True}

    mapped_status = _STATUS_MAP.get(raw_status)
    if mapped_status is None:
        log.warning(f"{provider}_webhook.unknown_status", extra={"status": raw_status})
        return {"received": True}

    asset_id: Any = None
    client_id: Any = None

    async with get_session() as session:
        await bypass_rls(session)

        result = await session.execute(
            text(
                "SELECT a.id, s.client_id "
                "FROM assets a JOIN sprints s ON a.sprint_id = s.id "
                "WHERE a.provider_job_id = :job_id "
                "LIMIT 1"
            ),
            {"job_id": job_id},
        )
        row = result.first()

        if row is None:
            log.info(f"{provider}_webhook.job_not_found", extra={"job_id": job_id})
            return {"received": True}

        asset_id, client_id = row

        await set_tenant_context(session, str(client_id))
        await session.execute(text("SET LOCAL row_security = on"))

        asset = await session.get(Asset, asset_id)
        if asset is None:
            return {"received": True}

        asset.generation_status = mapped_status
        if mapped_status == "completed" and media_url:
            asset.storage_status = "pending"

        await session.commit()

    log.info(
        f"{provider}_webhook.processed",
        extra={"job_id": job_id, "status": mapped_status},
    )

    audit_action = (
        AuditAction.WEBHOOK_JOB_COMPLETED
        if mapped_status == "completed"
        else AuditAction.WEBHOOK_JOB_FAILED
    )
    await emit_audit_event(
        action=audit_action,
        entity_type="asset",
        entity_id=str(asset_id),
        provider=provider,
        result=AuditResult.SUCCESS if mapped_status == "completed" else AuditResult.FAILED,
    )

    if mapped_status == "completed" and media_url:
        media_type = _PROVIDER_MEDIA_TYPE.get(provider, "video")
        if media_type == "image":
            upload_image_to_storage.delay(str(asset_id), media_url)
        else:
            upload_video_to_storage.delay(str(asset_id), media_url)

    return {"received": True}


@router.post("/higgsfield")
async def higgsfield_webhook(request: Request) -> dict[str, bool]:
    """Receive Higgsfield job completion callbacks.

    Verifies HMAC-SHA256 signature before processing. Returns 200 for all
    valid (signed) payloads so Higgsfield does not retry unnecessarily.
    Unknown job IDs are silently ignored (idempotent).
    """
    body = await request.body()
    headers = dict(request.headers)

    adapter = get_adapter("higgsfield")
    if not adapter.verify_webhook_signature(body, headers):
        log.warning("higgsfield_webhook.invalid_signature")
        return Response(content='{"error":"forbidden"}', status_code=403, media_type="application/json")  # type: ignore[return-value]

    payload: dict[str, Any] = {}
    try:
        payload = json.loads(body)
    except Exception:
        log.warning("higgsfield_webhook.invalid_json")
        return {"received": True}

    job_id: str = str(payload.get("generation_id") or payload.get("id") or "")
    raw_status: str = str(payload.get("status", "")).upper()
    output: dict[str, Any] = payload.get("output") or {}
    media_url: str | None = output.get("media_url") or None

    return await _process_provider_webhook("higgsfield", job_id, raw_status, media_url)


@router.post("/freepik")
async def freepik_webhook(request: Request) -> dict[str, bool]:
    """Receive Freepik image generation completion callbacks.

    Payload shape (Freepik AI text-to-image):
      { "id": "<task_id>", "status": "COMPLETED"|"FAILED",
        "generated": [{"url": "<image_url>"}] }
    """
    body = await request.body()
    headers = dict(request.headers)

    adapter = get_adapter("freepik")
    if not adapter.verify_webhook_signature(body, headers):
        log.warning("freepik_webhook.invalid_signature")
        return Response(content='{"error":"forbidden"}', status_code=403, media_type="application/json")  # type: ignore[return-value]

    payload: dict[str, Any] = {}
    try:
        payload = json.loads(body)
    except Exception:
        log.warning("freepik_webhook.invalid_json")
        return {"received": True}

    job_id: str = str(payload.get("id") or payload.get("taskId") or "")
    raw_status: str = str(payload.get("status", "")).upper()

    # Freepik returns images under "generated" list
    generated: list[dict[str, Any]] = payload.get("generated") or []
    media_url: str | None = generated[0].get("url") if generated else None

    return await _process_provider_webhook("freepik", job_id, raw_status, media_url)


@router.post("/magnific")
async def magnific_webhook(request: Request) -> dict[str, bool]:
    """Receive Magnific upscale completion callbacks.

    Payload shape (Magnific upscaling):
      { "id": "<job_id>", "status": "completed"|"failed",
        "output_url": "<upscaled_image_url>" }
    """
    body = await request.body()
    headers = dict(request.headers)

    adapter = get_adapter("magnific")
    if not adapter.verify_webhook_signature(body, headers):
        log.warning("magnific_webhook.invalid_signature")
        return Response(content='{"error":"forbidden"}', status_code=403, media_type="application/json")  # type: ignore[return-value]

    payload: dict[str, Any] = {}
    try:
        payload = json.loads(body)
    except Exception:
        log.warning("magnific_webhook.invalid_json")
        return {"received": True}

    job_id: str = str(payload.get("id") or payload.get("job_id") or "")
    raw_status: str = str(payload.get("status", ""))

    # Magnific returns the result under "output_url" or "url"
    media_url: str | None = payload.get("output_url") or payload.get("url") or None

    return await _process_provider_webhook("magnific", job_id, raw_status, media_url)
