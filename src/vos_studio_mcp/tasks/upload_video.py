"""Celery task — download from provider CDN and upload to R2 (Issue #6 item D)."""

import asyncio
import logging
from typing import Any

from vos_studio_mcp.services import storage
from vos_studio_mcp.services.database import get_asset_with_client, get_session
from vos_studio_mcp.tasks.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60, name="tasks.upload_video_to_storage")  # type: ignore[untyped-decorator]
def upload_video_to_storage(self: Any, asset_id: str, media_url: str) -> None:
    """Download the generated video from the provider CDN and upload to R2.

    On success: updates asset.storage_url with the permanent R2 URL.
    On unrecoverable failure: marks asset.generation_status = 'failed'
    and does not retry (avoids infinite loops on permanent errors).
    """
    try:
        client_id = asyncio.run(_get_client_id(asset_id))
        if not client_id:
            log.warning("upload_video_to_storage.asset_not_found", extra={"asset_id": asset_id})
            return

        data = storage.download_video(media_url)
        public_url = storage.upload_video(data, asset_id, client_id)
        asyncio.run(_update_storage_url(asset_id, public_url))
        log.info("upload_video_to_storage.done", extra={"asset_id": asset_id})

    except Exception as exc:
        log.error(
            "upload_video_to_storage.failed",
            extra={"asset_id": asset_id, "error": str(exc)},
        )
        try:
            raise self.retry(exc=exc)
        except Exception:
            asyncio.run(_mark_upload_failed(asset_id))


async def _get_client_id(asset_id: str) -> str | None:
    async with get_session() as session:
        _asset, client_id = await get_asset_with_client(session, asset_id)
        return client_id


async def _update_storage_url(asset_id: str, public_url: str) -> None:
    async with get_session() as session:
        asset, _ = await get_asset_with_client(session, asset_id)
        if asset is not None:
            asset.storage_url = public_url
            asset.generation_status = "completed"
            await session.commit()


async def _mark_upload_failed(asset_id: str) -> None:
    async with get_session() as session:
        asset, _ = await get_asset_with_client(session, asset_id)
        if asset is not None:
            asset.generation_status = "failed"
            await session.commit()
