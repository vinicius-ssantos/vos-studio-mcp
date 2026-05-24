"""Outbound webhook notifications for job completion events (Issue #33).

When a video asset reaches a terminal state (completed or failed),
this service POSTs a signed JSON payload to the client's webhook_url (if set).

Payload shape (stable, versioned):
    {
      "event": "asset.completed" | "asset.failed" | "asset.upload_failed",
      "schema_version": "1",
      "asset_id": "<uuid>",
      "sprint_id": "<uuid>",
      "client_id": "<uuid>",
      "generation_status": "completed" | "failed",
      "storage_status": "stored" | "failed" | "pending",
      "storage_url": "<url or null>",
      "provider_job_id": "<str or null>",
      "timestamp": "<ISO 8601 UTC>"
    }

The payload is signed with HMAC-SHA256 using the per-client
OUTBOUND_WEBHOOK_SECRET env var (falls back to a shared secret if not set).
The signature is sent in the X-VOS-Signature header as "sha256=<hex>".

Security notes:
- Shared secret is a configuration value, never logged or included in responses.
- The target URL is stored in the DB (client.webhook_url) — operators set it.
- Delivery is best-effort: failures are logged but do not affect job outcome.
- A 3-second timeout prevents slow receivers from blocking task workers.
"""

import datetime
import hashlib
import hmac
import json
import logging

import httpx

from vos_studio_mcp.config.env import get_settings

log = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 3.0
_SCHEMA_VERSION = "1"


def _build_payload(
    event: str,
    asset_id: str,
    sprint_id: str,
    client_id: str,
    generation_status: str,
    storage_status: str,
    storage_url: str | None,
    provider_job_id: str | None,
) -> dict[str, object]:
    return {
        "event": event,
        "schema_version": _SCHEMA_VERSION,
        "asset_id": asset_id,
        "sprint_id": sprint_id,
        "client_id": client_id,
        "generation_status": generation_status,
        "storage_status": storage_status,
        "storage_url": storage_url,
        "provider_job_id": provider_job_id,
        "timestamp": datetime.datetime.now(tz=datetime.UTC).isoformat(),
    }


def _sign_payload(body: bytes, secret: str) -> str:
    """Return 'sha256=<hex>' for the HMAC-SHA256 of *body* using *secret*."""
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


async def notify_job_completed(
    asset_id: str,
    sprint_id: str,
    client_id: str,
    webhook_url: str,
    storage_url: str | None,
    provider_job_id: str | None,
    storage_status: str = "stored",
) -> None:
    """POST an asset.completed notification to *webhook_url*.

    Silently swallows all network errors — the caller should not fail because
    of a third-party endpoint being unreachable.
    """
    try:
        await _deliver(
            event="asset.completed",
            webhook_url=webhook_url,
            asset_id=asset_id,
            sprint_id=sprint_id,
            client_id=client_id,
            generation_status="completed",
            storage_status=storage_status,
            storage_url=storage_url,
            provider_job_id=provider_job_id,
        )
    except Exception as exc:
        log.warning(
            "outbound_webhook.delivery_failed",
            extra={"asset_id": asset_id, "event": "asset.completed", "error": str(exc)},
        )


async def notify_job_failed(
    asset_id: str,
    sprint_id: str,
    client_id: str,
    webhook_url: str,
    provider_job_id: str | None,
    event: str = "asset.failed",
) -> None:
    """POST an asset.failed or asset.upload_failed notification to *webhook_url*."""
    try:
        await _deliver(
            event=event,
            webhook_url=webhook_url,
            asset_id=asset_id,
            sprint_id=sprint_id,
            client_id=client_id,
            generation_status="failed",
            storage_status="failed",
            storage_url=None,
            provider_job_id=provider_job_id,
        )
    except Exception as exc:
        log.warning(
            "outbound_webhook.delivery_failed",
            extra={"asset_id": asset_id, "event": event, "error": str(exc)},
        )


async def _deliver(
    event: str,
    webhook_url: str,
    asset_id: str,
    sprint_id: str,
    client_id: str,
    generation_status: str,
    storage_status: str,
    storage_url: str | None,
    provider_job_id: str | None,
) -> None:
    payload = _build_payload(
        event=event,
        asset_id=asset_id,
        sprint_id=sprint_id,
        client_id=client_id,
        generation_status=generation_status,
        storage_status=storage_status,
        storage_url=storage_url,
        provider_job_id=provider_job_id,
    )
    body = json.dumps(payload, separators=(",", ":")).encode()
    secret = get_settings().outbound_webhook_secret
    signature = _sign_payload(body, secret) if secret else ""

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if signature:
        headers["X-VOS-Signature"] = signature

    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        response = await client.post(webhook_url, content=body, headers=headers)

    # Raise so that _deliver_async (Celery path) can retry on non-2xx.
    # The public helpers (notify_job_completed / notify_job_failed) that need
    # best-effort / swallowing behaviour wrap this call in their own try/except.
    if not response.is_success:
        log.warning(
            "outbound_webhook.non_2xx",
            extra={
                "asset_id": asset_id,
                "event": event,
                "status_code": response.status_code,
            },
        )
        response.raise_for_status()
    else:
        log.info(
            "outbound_webhook.delivered",
            extra={"asset_id": asset_id, "event": event},
        )
