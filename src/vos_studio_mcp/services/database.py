"""Async database session factory (ADR-0007)."""

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import InternalError as SAInternalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from db.models import Asset
from vos_studio_mcp.config.env import get_settings
from vos_studio_mcp.errors import ErrorCode, VosError

_engine = create_async_engine(
    get_settings().database_url,
    echo=False,
    pool_pre_ping=True,
    poolclass=NullPool,
    connect_args={
        "prepared_statement_cache_size": 0,
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
    },
)
_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    _engine, expire_on_commit=False
)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session.

    Maps PostgreSQL row-level security violations to VosError(RLS_DENIED) so
    that any code path that accidentally bypasses the auth guard surfaces a
    clean, typed error rather than an unhandled 500.
    """
    async with _session_factory() as session:
        try:
            yield session
        except SAInternalError as exc:
            if "row-level security" in str(exc.orig).lower():
                raise VosError(
                    ErrorCode.RLS_DENIED,
                    "Access denied: the database rejected the query due to a "
                    "row-level security policy violation.",
                ) from exc
            raise


async def set_tenant_context(session: AsyncSession, client_id: str) -> None:
    """Set the Postgres session variable used by RLS policies (ADR-0018, ADR-0023)."""
    await session.execute(
        text("SELECT set_config('app.current_client_id', :cid, TRUE)"),
        {"cid": client_id},
    )


async def get_asset_with_client(
    session: AsyncSession, asset_id: str
) -> tuple[Asset | None, str | None]:
    """Look up an Asset by ID and return (asset, client_id).

    Calls the SECURITY DEFINER function vos_get_asset_client_id to retrieve
    the owning client_id without requiring BYPASSRLS on the connection role
    (ADR-0040), then sets the RLS tenant context before fetching the full
    ORM object so subsequent session operations are properly isolated.
    """
    result = await session.execute(
        text("SELECT vos_get_asset_client_id(:asset_id)"),
        {"asset_id": asset_id},
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None, None

    client_id = str(row)
    await set_tenant_context(session, client_id)
    asset = await session.get(Asset, uuid.UUID(asset_id))
    return asset, client_id


async def set_tenant_context_from_sprint(session: AsyncSession, sprint_id: str) -> str:
    """Look up a sprint's client_id and set the RLS tenant context.

    Calls the SECURITY DEFINER function vos_get_sprint_client_id to retrieve
    the client_id without requiring BYPASSRLS on the connection role (ADR-0040).
    Returns the client_id string. Raises LookupError if the sprint is not found.
    """
    result = await session.execute(
        text("SELECT vos_get_sprint_client_id(:sprint_id)"),
        {"sprint_id": sprint_id},
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise LookupError(f"Sprint {sprint_id} not found")
    client_id = str(row)
    await set_tenant_context(session, client_id)
    return client_id


async def bypass_rls(session: AsyncSession) -> None:
    """Disable row-level security for the current transaction.

    Requires the DB user to have BYPASSRLS privilege (Supabase service role
    in production; postgres superuser in development).

    Used by scheduled/system-wide tasks (quota reset, library tier refresh,
    performance rollup, stale job cleanup) that operate across all tenants
    by design.  NOT used for the provider webhook ingress bootstrap path —
    that uses SECURITY DEFINER functions instead (ADR-0040 step 1).

    Step 2 of ADR-0040 will eliminate this function by providing
    SECURITY DEFINER functions or a separate privileged connection for each
    remaining cross-tenant operation.
    """
    await session.execute(text("SET LOCAL row_security = off"))


async def get_asset_by_job_id(
    session: AsyncSession, job_id: str
) -> tuple[str | None, str | None]:
    """Return (asset_id, client_id) for a provider job ID, bypassing RLS.

    Calls the SECURITY DEFINER function vos_get_asset_by_job_id so the
    webhook ingress can bootstrap tenant context without BYPASSRLS on the
    connection role (ADR-0040).  Returns (None, None) if not found.
    """
    result = await session.execute(
        text("SELECT asset_id, client_id FROM vos_get_asset_by_job_id(:job_id)"),
        {"job_id": job_id},
    )
    row = result.first()
    if row is None:
        return None, None
    return str(row[0]), str(row[1])


async def get_asset_notification_context(
    asset_id: str,
) -> tuple[str | None, str | None, str | None]:
    """Return (sprint_id, client_id, webhook_url) for *asset_id*.

    Calls the SECURITY DEFINER function vos_get_asset_notification_context
    so the upload task can fan out webhook delivery without requiring
    BYPASSRLS on the connection role (ADR-0040).
    Returns (None, None, None) if the asset is not found.
    """
    async with get_session() as session:
        result = await session.execute(
            text("SELECT sprint_id, client_id, webhook_url FROM vos_get_asset_notification_context(:asset_id)"),
            {"asset_id": asset_id},
        )
        row = result.first()
        if row is None:
            return None, None, None
        return str(row[0]), str(row[1]), row[2]
