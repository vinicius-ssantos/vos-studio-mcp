"""Server status and component health services."""

import asyncio
import logging
import time

from sqlalchemy import text

from vos_studio_mcp import __version__
from vos_studio_mcp.config.env import Settings, get_settings
from vos_studio_mcp.schemas.status import ComponentStatus, HealthResponse, ServerStatus

log = logging.getLogger(__name__)


def get_server_status(settings: Settings) -> ServerStatus:
    """Return a compact status payload."""
    return ServerStatus(
        service=settings.mcp_server_name,
        version=__version__,
        next_action="create_client",
    )


async def _check_database() -> ComponentStatus:
    """Ping the database with a SELECT 1."""
    from vos_studio_mcp.services.database import get_session

    start = time.monotonic()
    try:
        async with get_session() as session:
            await session.execute(text("SELECT 1"))
        latency_ms = (time.monotonic() - start) * 1000
        return ComponentStatus(status="ok", latency_ms=round(latency_ms, 1))
    except Exception as exc:
        log.warning("health_check.database_error", extra={"error": str(exc)})
        return ComponentStatus(status="down", detail="connection failed")


async def _check_redis() -> ComponentStatus:
    """Ping Redis using the async client."""
    import redis.asyncio as aioredis

    settings = get_settings()
    start = time.monotonic()
    client: aioredis.Redis | None = None
    try:
        client = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)  # type: ignore[no-untyped-call]
        await client.ping()
        latency_ms = (time.monotonic() - start) * 1000
        return ComponentStatus(status="ok", latency_ms=round(latency_ms, 1))
    except Exception as exc:
        log.warning("health_check.redis_error", extra={"error": str(exc)})
        return ComponentStatus(status="down", detail="ping failed")
    finally:
        if client is not None:
            await client.aclose()


async def _check_celery_worker() -> ComponentStatus:
    """Check if at least one Celery worker is online via broker ping."""
    from vos_studio_mcp.tasks.celery_app import celery_app

    def _ping() -> dict[str, object] | None:
        try:
            inspector = celery_app.control.inspect(timeout=2.0)
            raw = inspector.ping()  # celery inspect returns untyped Any
            if raw is None:
                return None
            return dict(raw)
        except Exception:
            return None

    try:
        result = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, _ping),
            timeout=3.0,
        )
        if result:
            worker_count = len(result)
            return ComponentStatus(
                status="ok",
                detail=f"{worker_count} worker{'s' if worker_count != 1 else ''} online",
            )
        return ComponentStatus(status="down", detail="no workers responded")
    except TimeoutError:
        return ComponentStatus(status="down", detail="ping timed out")
    except Exception as exc:
        log.warning("health_check.celery_error", extra={"error": str(exc)})
        return ComponentStatus(status="down", detail="inspection failed")


async def get_health() -> HealthResponse:
    """Run all component checks concurrently and aggregate results."""
    settings = get_settings()

    db_status, redis_status, worker_status = await asyncio.gather(
        _check_database(),
        _check_redis(),
        _check_celery_worker(),
    )

    components = {
        "database": db_status,
        "redis": redis_status,
        "celery_worker": worker_status,
    }

    # Overall status: "down" if any critical component fails, "degraded" if worker is down
    if db_status.status == "down" or redis_status.status == "down":
        overall = "down"
    elif worker_status.status == "down":
        overall = "degraded"
    else:
        overall = "ok"

    return HealthResponse(
        status=overall,
        service=settings.mcp_server_name,
        version=__version__,
        components=components,
    )
