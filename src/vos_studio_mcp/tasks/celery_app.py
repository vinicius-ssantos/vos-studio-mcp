"""Celery application instance for background jobs."""

from celery import Celery

from vos_studio_mcp.config.env import get_settings

settings = get_settings()

celery_app = Celery(
    "vos_studio_mcp",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
