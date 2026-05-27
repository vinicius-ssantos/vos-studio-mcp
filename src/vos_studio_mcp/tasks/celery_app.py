"""Celery application instance for background jobs."""

from celery import Celery
from celery.schedules import crontab

from vos_studio_mcp.config.env import get_settings
from vos_studio_mcp.tasks.base import CorrelatedTask

settings = get_settings()

celery_app = Celery(
    "vos_studio_mcp",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    task_cls=CorrelatedTask,
)

# ---------------------------------------------------------------------------
# Beat schedule — periodic tasks (ADR-0021, Issue #28)
# ---------------------------------------------------------------------------
celery_app.conf.beat_schedule = {
    # Daily at 03:00 UTC — aggregate PerformanceRecord rows into brand_kit.performance_memory
    "rollup-performance-memory-daily": {
        "task": "tasks.rollup_performance_memory",
        "schedule": crontab(hour=3, minute=0),
    },
    # Daily at 03:30 UTC — recalculate prompt template performance tiers
    "refresh-library-tiers-daily": {
        "task": "tasks.refresh_library_tiers",
        "schedule": crontab(hour=3, minute=30),
    },
    # Weekly on Sunday at 04:00 UTC — remove stale failed API-generated assets
    "cleanup-stale-jobs-weekly": {
        "task": "tasks.cleanup_stale_jobs",
        "schedule": crontab(hour=4, minute=0, day_of_week="sunday"),
    },
}
celery_app.conf.timezone = "UTC"
