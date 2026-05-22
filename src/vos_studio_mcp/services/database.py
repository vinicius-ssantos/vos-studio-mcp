"""Async database session factory (ADR-0007)."""

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from db.models import Asset
from vos_studio_mcp.config.env import get_settings

_engine = create_async_engine(get_settings().database_url, echo=False, pool_pre_ping=True)
_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    _engine, expire_on_commit=False
)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with _session_factory() as session:
        yield session


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


async def bypass_rls(session: AsyncSession) -> None:
    """Disable row-level security for the current transaction.

    Requires the DB user to have BYPASSRLS privilege (Supabase service role
    in production; postgres superuser in development). Used exclusively by
    the webhook handler to look up assets by provider_job_id without a
    client context. Call set_tenant_context afterwards to re-apply RLS for
    any subsequent writes.
    """
    await session.execute(text("SET LOCAL row_security = off"))
