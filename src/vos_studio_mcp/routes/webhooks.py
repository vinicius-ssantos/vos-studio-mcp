"""Webhook receiver for provider callbacks (ADR-0028)."""

import json
import logging
from typing import Any, Literal

from fastapi import APIRouter, Request, Response
from sqlalchemy import text

from db.models import Asset
from vos_studio_mcp.services.database import bypass_rls, get_session, set_tenant_context
from vos_studio_mcp.services.providers import get_adapter
from vos_studio_mcp.tasks.upload_video import upload_video_to_storage

log = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks")

_STATUS_MAP: dict[str, Literal["pending", "processing", "completed", "failed"]] = {
    "QUEUED": "pending",
    "PROCESSING": "processing",
    "COMPLETED": "completed",
    "FAILED": "failed",
    "ERROR": "failed",
}


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

    if not job_id:
        log.warning("higgsfield_webhook.missing_job_id")
        return {"received": True}

    mapped_status = _STATUS_MAP.get(raw_status)
    if mapped_status is None:
        log.warning("higgsfield_webhook.unknown_status", extra={"status": raw_status})
        return {"received": True}

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
            log.info("higgsfield_webhook.job_not_found", extra={"job_id": job_id})
            return {"received": True}

        asset_id, client_id = row

        await set_tenant_context(session, str(client_id))
        await session.execute(text("SET LOCAL row_security = on"))

        asset = await session.get(Asset, asset_id)
        if asset is None:
            return {"received": True}

        asset.generation_status = mapped_status
        if mapped_status == "completed" and media_url:
            asset.storage_url = media_url

        await session.commit()

    log.info(
        "higgsfield_webhook.processed",
        extra={"job_id": job_id, "status": mapped_status},
    )

    if mapped_status == "completed" and media_url:
        upload_video_to_storage.delay(str(asset_id), media_url)

    return {"received": True}
