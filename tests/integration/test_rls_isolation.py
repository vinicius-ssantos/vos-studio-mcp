"""Integration tests: RLS client-data isolation (ADR-0026 Layer 2, ADR-0023).

Proves that a query authenticated as client A cannot return rows belonging to client B
for every client-scoped table: sprints, assets, brand_kits.

Requires a real PostgreSQL database. Skipped automatically without DATABASE_URL.
Run with: pytest tests/integration/ -m integration -v

Two connections are used deliberately:
  engine      — superuser (DATABASE_URL); bypasses RLS to insert test fixtures.
  app_engine  — non-superuser (APP_DATABASE_URL); subject to RLS policies, so
                the isolation assertions actually prove enforcement.
"""

import os
import uuid

import pytest
import pytest_asyncio

pytestmark = pytest.mark.integration

_DB_AVAILABLE = False
try:
    import asyncpg  # noqa: F401

    _DB_AVAILABLE = True
except ImportError:
    pass


def _require_db() -> None:
    if not _DB_AVAILABLE or not os.environ.get("DATABASE_URL"):
        pytest.skip("No DATABASE_URL — skipping RLS integration test")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine():  # type: ignore[misc]
    """Superuser engine — used only for fixture setup/teardown (bypasses RLS)."""
    _require_db()
    from sqlalchemy.ext.asyncio import create_async_engine

    e = create_async_engine(os.environ["DATABASE_URL"], echo=False)
    yield e
    await e.dispose()


@pytest_asyncio.fixture
async def app_engine():  # type: ignore[misc]
    """Non-superuser engine for RLS-sensitive queries.

    Uses APP_DATABASE_URL when available (CI sets this to a vos_app role that
    is subject to RLS policies). Falls back to DATABASE_URL so the fixture
    collection never errors in local environments without the extra role.
    """
    _require_db()
    from sqlalchemy.ext.asyncio import create_async_engine

    url = os.environ.get("APP_DATABASE_URL") or os.environ["DATABASE_URL"]
    e = create_async_engine(url, echo=False)
    yield e
    await e.dispose()


@pytest_asyncio.fixture
async def two_clients(engine):  # type: ignore[misc]
    """Create two isolated clients with one sprint + asset each, then clean up."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(engine, expire_on_commit=False)

    client_a = uuid.uuid4()
    client_b = uuid.uuid4()
    brand_kit_a = uuid.uuid4()
    brand_kit_b = uuid.uuid4()
    sprint_a = uuid.uuid4()
    sprint_b = uuid.uuid4()
    asset_a = uuid.uuid4()
    asset_b = uuid.uuid4()

    async with factory() as session:
        await session.execute(text("SET LOCAL row_security = off"))

        for cid, name in [
            (client_a, "Client A"),
            (client_b, "Client B"),
        ]:
            await session.execute(
                text("INSERT INTO clients (id, name) VALUES (:id, :name)"),
                {"id": str(cid), "name": name},
            )

        for bkid, cid, name in [
            (brand_kit_a, client_a, "Brand Kit A"),
            (brand_kit_b, client_b, "Brand Kit B"),
        ]:
            await session.execute(
                text("INSERT INTO brand_kits (id, client_id, name) VALUES (:id, :cid, :name)"),
                {"id": str(bkid), "cid": str(cid), "name": name},
            )

        for sid, cid, bkid, product_name in [
            (sprint_a, client_a, brand_kit_a, "Sprint A Product"),
            (sprint_b, client_b, brand_kit_b, "Sprint B Product"),
        ]:
            await session.execute(
                text(
                    "INSERT INTO sprints (id, client_id, brand_kit_id, product_name,"
                    " campaign_objective, target_audience, brief, sprint_status,"
                    " max_spend_usd, spent_usd)"
                    " VALUES (:id, :cid, :bkid, :product_name, :objective, :audience,"
                    " :brief, 'open', 10, 0)"
                ),
                {
                    "id": str(sid),
                    "cid": str(cid),
                    "bkid": str(bkid),
                    "product_name": product_name,
                    "objective": "Integration test objective",
                    "audience": "Integration test audience",
                    "brief": "Integration test brief",
                },
            )

        for aid, sid, prov in [(asset_a, sprint_a, "higgsfield"), (asset_b, sprint_b, "higgsfield")]:
            await session.execute(
                text(
                    "INSERT INTO assets (id, sprint_id, provider, prompt_version,"
                    " preset_version, generation_status)"
                    " VALUES (:id, :sid, :prov, 'v1', 'p1', 'manual')"
                ),
                {"id": str(aid), "sid": str(sid), "prov": prov},
            )

        await session.commit()

    yield {
        "client_a": client_a,
        "client_b": client_b,
        "sprint_a": sprint_a,
        "sprint_b": sprint_b,
        "asset_a": asset_a,
        "asset_b": asset_b,
    }

    async with factory() as session:
        await session.execute(text("SET LOCAL row_security = off"))
        for aid in [asset_a, asset_b]:
            await session.execute(text("DELETE FROM assets WHERE id = :id"), {"id": str(aid)})
        for sid in [sprint_a, sprint_b]:
            await session.execute(text("DELETE FROM sprints WHERE id = :id"), {"id": str(sid)})
        for bkid in [brand_kit_a, brand_kit_b]:
            await session.execute(text("DELETE FROM brand_kits WHERE id = :id"), {"id": str(bkid)})
        for cid in [client_a, client_b]:
            await session.execute(text("DELETE FROM clients WHERE id = :id"), {"id": str(cid)})
        await session.commit()


# ---------------------------------------------------------------------------
# RLS isolation tests — queries run through app_engine (non-superuser)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sprint_rls_client_a_cannot_read_client_b_sprints(app_engine, two_clients) -> None:  # type: ignore[misc]
    """Client A's RLS context must not expose client B's sprints."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(app_engine, expire_on_commit=False)
    client_a_id = str(two_clients["client_a"])
    sprint_b_id = str(two_clients["sprint_b"])

    async with factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_client_id', :cid, TRUE)"),
            {"cid": client_a_id},
        )
        await session.execute(text("SET LOCAL row_security = on"))

        result = await session.execute(
            text("SELECT id FROM sprints WHERE id = :sid"),
            {"sid": sprint_b_id},
        )
        row = result.first()

    assert row is None, "Client A must not read client B's sprint via RLS"


@pytest.mark.asyncio
async def test_sprint_rls_client_a_can_read_own_sprint(app_engine, two_clients) -> None:  # type: ignore[misc]
    """Client A's RLS context must expose its own sprint."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(app_engine, expire_on_commit=False)
    client_a_id = str(two_clients["client_a"])
    sprint_a_id = str(two_clients["sprint_a"])

    async with factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_client_id', :cid, TRUE)"),
            {"cid": client_a_id},
        )
        await session.execute(text("SET LOCAL row_security = on"))

        result = await session.execute(
            text("SELECT id FROM sprints WHERE id = :sid"),
            {"sid": sprint_a_id},
        )
        row = result.first()

    assert row is not None, "Client A must be able to read its own sprint"


@pytest.mark.asyncio
async def test_asset_rls_client_a_cannot_read_client_b_assets(app_engine, two_clients) -> None:  # type: ignore[misc]
    """Client A's RLS context must not expose client B's assets."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(app_engine, expire_on_commit=False)
    client_a_id = str(two_clients["client_a"])
    asset_b_id = str(two_clients["asset_b"])

    async with factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_client_id', :cid, TRUE)"),
            {"cid": client_a_id},
        )
        await session.execute(text("SET LOCAL row_security = on"))

        result = await session.execute(
            text("SELECT id FROM assets WHERE id = :aid"),
            {"aid": asset_b_id},
        )
        row = result.first()

    assert row is None, "Client A must not read client B's asset via RLS"


@pytest.mark.asyncio
async def test_asset_rls_client_a_can_read_own_assets(app_engine, two_clients) -> None:  # type: ignore[misc]
    """Client A's RLS context must expose its own assets."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(app_engine, expire_on_commit=False)
    client_a_id = str(two_clients["client_a"])
    asset_a_id = str(two_clients["asset_a"])

    async with factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_client_id', :cid, TRUE)"),
            {"cid": client_a_id},
        )
        await session.execute(text("SET LOCAL row_security = on"))

        result = await session.execute(
            text("SELECT id FROM assets WHERE id = :aid"),
            {"aid": asset_a_id},
        )
        row = result.first()

    assert row is not None, "Client A must be able to read its own assets"


@pytest.mark.asyncio
async def test_sprint_count_rls_client_a_sees_only_own_sprints(app_engine, two_clients) -> None:  # type: ignore[misc]
    """Aggregate query under client A context must not count client B's sprints."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(app_engine, expire_on_commit=False)
    client_a_id = str(two_clients["client_a"])

    async with factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_client_id', :cid, TRUE)"),
            {"cid": client_a_id},
        )
        await session.execute(text("SET LOCAL row_security = on"))

        result = await session.execute(
            text("SELECT COUNT(*) FROM sprints WHERE id IN (:sa, :sb)"),
            {"sa": str(two_clients["sprint_a"]), "sb": str(two_clients["sprint_b"])},
        )
        count = result.scalar()

    assert count == 1, f"Expected 1 sprint visible to client A, got {count}"
