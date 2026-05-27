"""Asset storage — upload to R2/S3 and download from provider CDN (ADR-0008)."""

import logging

import httpx

from vos_studio_mcp.config.env import get_settings

log = logging.getLogger(__name__)


def download_video(url: str) -> bytes:
    """Download video from a URL and return raw bytes."""
    with httpx.Client(timeout=300.0, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.content


def download_media(url: str) -> bytes:
    """Download any media (image or video) from a URL and return raw bytes."""
    with httpx.Client(timeout=300.0, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.content


def upload_image(data: bytes, asset_id: str, client_id: str, ext: str = "png") -> str:
    """Upload image bytes to the configured R2/S3 bucket.

    Returns the public URL of the uploaded object.
    """
    import boto3

    settings = get_settings()
    key = f"images/{client_id}/{asset_id}.{ext}"

    s3 = boto3.client(
        "s3",
        endpoint_url=settings.storage_endpoint,
        aws_access_key_id=settings.storage_access_key,
        aws_secret_access_key=settings.storage_secret_key,
        region_name="auto",
    )
    s3.put_object(
        Bucket=settings.storage_bucket,
        Key=key,
        Body=data,
        ContentType=f"image/{ext}",
    )

    public_url = f"{settings.storage_public_base_url.rstrip('/')}/{key}"
    log.info("storage.upload_image.done", extra={"asset_id": asset_id, "key": key})
    return public_url


def upload_video(data: bytes, asset_id: str, client_id: str) -> str:
    """Upload video bytes to the configured R2/S3 bucket.

    Returns the public URL of the uploaded object.
    Requires boto3 and a correctly configured storage_* env block.
    """
    import boto3  # imported lazily — not available in all environments

    settings = get_settings()
    key = f"videos/{client_id}/{asset_id}.mp4"

    s3 = boto3.client(
        "s3",
        endpoint_url=settings.storage_endpoint,
        aws_access_key_id=settings.storage_access_key,
        aws_secret_access_key=settings.storage_secret_key,
        region_name="auto",
    )
    s3.put_object(
        Bucket=settings.storage_bucket,
        Key=key,
        Body=data,
        ContentType="video/mp4",
    )

    public_url = f"{settings.storage_public_base_url.rstrip('/')}/{key}"
    log.info("storage.upload.done", extra={"asset_id": asset_id, "key": key})
    return public_url
