"""Async database session factory (ADR-0007)."""

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.exc import InternalError as SAInternalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from db.models import Asset
from vos_studio_mcp.config.env import get_settings
from vos_studio_mcp.errors import ErrorCode, VosError

_engine = create_async_engine(
    get_settings().database_url,
    echo=False,
    pool_pre_ping=True,
    connect_args={"prepared_statement_cache_size": 0},
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

    Bypasses RLS for the initial JOIN to retrieve client_id, then
    re-enables RLS with the correct tenant context before fetching
    the full ORM object. Returns (None, None) if the asset is not found.
    """
    await bypass_rls(session)
    result = await session.execute(
        text(
            "SELECT s.client_id FROM assets a "
            "JOIN sprints s ON a.sprint_id = s.id "
            "WHERE a.id = :asset_id LIMIT 1"
        ),
        {"asset_id": asset_id},
    )
    row = result.first()
    if row is None:
        return None, None

    client_id = str(row[0])
    await set_tenant_context(session, client_id)
    await session.execute(text("SET LOCAL row_security = on"))

    asset = await session.get(Asset, uuid.UUID(asset_id))
    return asset, client_id


async def set_tenant_context_from_sprint(session: AsyncSession, sprint_id: str) -> str:
    """Look up a sprint's client_id and set the RLS tenant context.

    Bypasses RLS to retrieve the client_id, then re-enables RLS with that context.
    Returns the client_id string. Raises LookupError if the sprint is not found.
    """
    await bypass_rls(session)
    result = await session.execute(
        text("SELECT client_id FROM sprints WHERE id = :sprint_id LIMIT 1"),
        {"sprint_id": sprint_id},
    )
    row = result.first()
    if row is None:
        raise LookupError(f"Sprint {sprint_id} not found")
    client_id = str(row[0])
    await set_tenant_context(session, client_id)
    await session.execute(text("SET LOCAL row_security = on"))
    return client_id


async def get_asset_notification_context(
    asset_id: str,
) -> tuple[str | None, str | None, str | None]:
    """Return (sprint_id, client_id, webhook_url) for *asset_id*.

    Bypasses RLS to retrieve the client's webhook_url.
    Returns (None, None, None) if the asset is not found.
    """
    async with get_session() as session:
        await bypass_rls(session)
        result = await session.execute(
            text(
                "SELECT a.sprint_id, s.client_id, c.webhook_url "
                "FROM assets a "
                "JOIN sprints s ON a.sprint_id = s.id "
                "JOIN clients c ON s.client_id = c.id "
                "WHERE a.id = :asset_id LIMIT 1"
            ),
            {"asset_id": asset_id},
        )
        row = result.first()
        if row is None:
            return None, None, None
        return str(row[0]), str(row[1]), row[2]


async def bypass_rls(session: AsyncSession) -> None:
    """Disable row-level security for the current transaction.

    Requires the DB user to have BYPASSRLS privilege (Supabase service role
    in production; postgres superuser in development). Used exclusively by
    the webhook handler to look up assets by provider_job_id without a
    client context. Call set_tenant_context afterwards to re-apply RLS for
    any subsequent writes.
    """
    await session.execute(text("SET LOCAL row_security = off"))
