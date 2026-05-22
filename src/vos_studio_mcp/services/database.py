"""Async database session factory (ADR-0007)."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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


async def bypass_rls(session: AsyncSession) -> None:
    """Disable row-level security for the current transaction.

    Requires the DB user to have BYPASSRLS privilege (Supabase service role
    in production; postgres superuser in development). Used exclusively by
    the webhook handler to look up assets by provider_job_id without a
    client context. Call set_tenant_context afterwards to re-apply RLS for
    any subsequent writes.
    """
    await session.execute(text("SET LOCAL row_security = off"))
