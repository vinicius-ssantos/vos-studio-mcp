"""Celery task — deliver outbound webhook notifications with exponential backoff.

Replaces the inline asyncio.run() calls in upload_video and poll_video with
a durable, retryable Celery task so that transient webhook endpoint failures
(5xx, timeout, DNS) don't silently drop the notification.

Retry policy
------------
  max_retries = 5
  backoff     = 30s * 2^attempt  →  30s, 60s, 120s, 240s, 480s (~13 min total)
  jitter      = ±10 s (prevents thundering-herd on mass failures)

After 5 retries the task is abandoned and a structured warning is logged.
The job outcome is NOT affected — this is a best-effort notification layer.
"""

import asyncio
import logging
import random
from typing import Any

from vos_studio_mcp.tasks.celery_app import celery_app

log = logging.getLogger(__name__)

_MAX_RETRIES = 5
_BASE_BACKOFF_SECONDS = 30
_JITTER_SECONDS = 10


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    max_retries=_MAX_RETRIES,
    name="tasks.deliver_webhook",
    acks_late=True,
)
def deliver_webhook(
    self: Any,
    *,
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
    """Deliver one webhook notification, retrying on failure.

    All keyword-only arguments map directly to the webhook payload fields so
    the task is self-contained — no DB look-up required at delivery time.
    """
    asyncio.run(
        _deliver_async(
            self,
            event=event,
            webhook_url=webhook_url,
            asset_id=asset_id,
            sprint_id=sprint_id,
            client_id=client_id,
            generation_status=generation_status,
            storage_status=storage_status,
            storage_url=storage_url,
            provider_job_id=provider_job_id,
        )
    )


async def _deliver_async(
    task: Any,
    *,
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
    from vos_studio_mcp.services.webhook_notifier import _deliver

    try:
        await _deliver(
            event=event,
            webhook_url=webhook_url,
            asset_id=asset_id,
            sprint_id=sprint_id,
            client_id=client_id,
            generation_status=generation_status,
            storage_status=storage_status,
            storage_url=storage_url,
            provider_job_id=provider_job_id,
        )
    except Exception as exc:
        attempt = task.request.retries
        if attempt >= _MAX_RETRIES:
            log.warning(
                "deliver_webhook.abandoned",
                extra={
                    "asset_id": asset_id,
                    "event": event,
                    "attempts": attempt + 1,
                },
            )
            return

        backoff = _BASE_BACKOFF_SECONDS * (2 ** attempt)
        jitter = random.uniform(-_JITTER_SECONDS, _JITTER_SECONDS)
        countdown = max(1, backoff + jitter)
        log.info(
            "deliver_webhook.retry",
            extra={
                "asset_id": asset_id,
                "event": event,
                "attempt": attempt + 1,
                "countdown_s": round(countdown),
                "error": str(exc),
            },
        )
        raise task.retry(exc=exc, countdown=countdown) from exc


# ---------------------------------------------------------------------------
# Convenience helpers — called from upload_video and poll_video
# ---------------------------------------------------------------------------

def enqueue_webhook_completed(
    asset_id: str,
    sprint_id: str,
    client_id: str,
    webhook_url: str,
    storage_url: str | None,
    provider_job_id: str | None,
    storage_status: str = "stored",
) -> None:
    """Enqueue an asset.completed notification via Celery."""
    deliver_webhook.delay(
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


def enqueue_webhook_failed(
    asset_id: str,
    sprint_id: str,
    client_id: str,
    webhook_url: str,
    provider_job_id: str | None,
    event: str = "asset.failed",
) -> None:
    """Enqueue an asset.failed or asset.upload_failed notification via Celery."""
    deliver_webhook.delay(
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
