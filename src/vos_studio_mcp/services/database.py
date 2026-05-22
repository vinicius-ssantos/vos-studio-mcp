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
