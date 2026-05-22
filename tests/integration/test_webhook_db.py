"""Integration tests: webhook → DB update path (Issue #6 acceptance criterion).

These tests require a real PostgreSQL database with the migration schema applied.
They are skipped automatically when DATABASE_URL is not reachable.

Run explicitly with:
    pytest tests/integration/ -m integration -v
"""

import hashlib
import hmac
import json
import os
import uuid

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# DB availability guard
# ---------------------------------------------------------------------------

_DB_AVAILABLE = False

try:
    import asyncpg  # noqa: F401 — presence check only

    _DB_AVAILABLE = True
except ImportError:
    pass


def _require_db() -> None:
    if not _DB_AVAILABLE or not os.environ.get("DATABASE_URL"):
        pytest.skip("No DATABASE_URL — skipping integration test")


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session():  # type: ignore[misc]
    """Async SQLAlchemy session connected to the real DB."""
    _require_db()

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(os.environ["DATABASE_URL"], echo=False, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def test_asset(db_session):  # type: ignore[misc]
    """Create a minimal client → sprint → asset fixture, then clean up."""
    from sqlalchemy import text

    # Use postgres superuser to bypass RLS for fixture setup
    await db_session.execute(text("SET LOCAL row_security = off"))

    client_id = uuid.uuid4()
    brand_kit_id = uuid.uuid4()
    sprint_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    job_id = f"integ-{uuid.uuid4().hex[:8]}"

    await db_session.execute(
        text(
            "INSERT INTO clients (id, name, industry) VALUES (:id, :name, :industry)"
            " ON CONFLICT DO NOTHING"
        ),
        {"id": str(client_id), "name": "Integ Client", "industry": "integration-test"},
    )
    await db_session.execute(
        text("INSERT INTO brand_kits (id, client_id, name) VALUES (:id, :cid, :name) ON CONFLICT DO NOTHING"),
        {"id": str(brand_kit_id), "cid": str(client_id), "name": "Integration Brand Kit"},
    )
    await db_session.execute(
        text(
            "INSERT INTO sprints (id, client_id, brand_kit_id, product_name,"
            " campaign_objective, target_audience, brief, sprint_status,"
            " max_spend_usd, spent_usd)"
            " VALUES (:id, :cid, :bkid, :product_name, :objective, :audience,"
            " :brief, :status, :max, :spent)"
            " ON CONFLICT DO NOTHING"
        ),
        {
            "id": str(sprint_id),
            "cid": str(client_id),
            "bkid": str(brand_kit_id),
            "product_name": "Integration Product",
            "objective": "Integration test objective",
            "audience": "Integration test audience",
            "brief": "Integration test brief",
            "status": "open",
            "max": 10.0,
            "spent": 0.0,
        },
    )
    await db_session.execute(
        text(
            "INSERT INTO assets (id, sprint_id, provider, prompt_version, preset_version,"
            " generation_status, provider_job_id)"
            " VALUES (:id, :sid, :prov, :pv, :ppv, :status, :job)"
            " ON CONFLICT DO NOTHING"
        ),
        {
            "id": str(asset_id),
            "sid": str(sprint_id),
            "prov": "higgsfield",
            "pv": "v1",
            "ppv": "p1",
            "status": "pending",
            "job": job_id,
        },
    )
    await db_session.commit()

    yield {"asset_id": asset_id, "sprint_id": sprint_id, "client_id": client_id, "job_id": job_id}

    # Cleanup
    await db_session.execute(text("SET LOCAL row_security = off"))
    await db_session.execute(text("DELETE FROM assets WHERE id = :id"), {"id": str(asset_id)})
    await db_session.execute(text("DELETE FROM sprints WHERE id = :id"), {"id": str(sprint_id)})
    await db_session.execute(text("DELETE FROM brand_kits WHERE id = :id"), {"id": str(brand_kit_id)})
    await db_session.execute(
        text("DELETE FROM clients WHERE id = :id"), {"id": str(client_id)}
    )
    await db_session.commit()


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def _post_higgsfield_webhook(body: bytes, signature: str):  # type: ignore[no-untyped-def]
    """Post to the webhook ASGI app without crossing event loops."""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from vos_studio_mcp.routes.webhooks import router

    app = FastAPI()
    app.include_router(router)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/webhooks/higgsfield",
            content=body,
            headers={"X-Higgsfield-Signature": signature},
        )

    from vos_studio_mcp.services import database

    await database._engine.dispose()
    return response


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_completed_updates_generation_status(test_asset, db_session) -> None:  # type: ignore[misc]
    """COMPLETED webhook payload must flip generation_status to 'completed'."""
    from vos_studio_mcp.config.env import get_settings

    secret = get_settings().webhook_secret_higgsfield or "test-secret"
    body = json.dumps(
        {
            "generation_id": test_asset["job_id"],
            "status": "COMPLETED",
            "output": {"media_url": "https://cdn.higgsfield.ai/integ.mp4"},
        }
    ).encode()

    resp = await _post_higgsfield_webhook(body, _sign(secret, body))

    assert resp.status_code == 200
    assert resp.json() == {"received": True}

    from sqlalchemy import text

    await db_session.execute(text("SET LOCAL row_security = off"))
    result = await db_session.execute(
        text("SELECT generation_status, storage_url FROM assets WHERE id = :id"),
        {"id": str(test_asset["asset_id"])},
    )
    row = result.first()
    assert row is not None
    assert row[0] == "completed"
    assert row[1] == "https://cdn.higgsfield.ai/integ.mp4"


@pytest.mark.asyncio
async def test_webhook_failed_updates_generation_status(test_asset, db_session) -> None:  # type: ignore[misc]
    """FAILED webhook payload must flip generation_status to 'failed'."""
    from vos_studio_mcp.config.env import get_settings

    secret = get_settings().webhook_secret_higgsfield or "test-secret"
    body = json.dumps(
        {"generation_id": test_asset["job_id"], "status": "FAILED", "output": {}}
    ).encode()

    resp = await _post_higgsfield_webhook(body, _sign(secret, body))

    assert resp.status_code == 200

    from sqlalchemy import text

    await db_session.execute(text("SET LOCAL row_security = off"))
    result = await db_session.execute(
        text("SELECT generation_status FROM assets WHERE id = :id"),
        {"id": str(test_asset["asset_id"])},
    )
    row = result.first()
    assert row is not None
    assert row[0] == "failed"


@pytest.mark.asyncio
async def test_webhook_unknown_job_id_is_idempotent(db_session) -> None:  # type: ignore[misc]
    """Payload with an unknown generation_id must return 200 without modifying the DB."""
    from vos_studio_mcp.config.env import get_settings

    secret = get_settings().webhook_secret_higgsfield or "test-secret"
    body = json.dumps(
        {
            "generation_id": "gen-does-not-exist-xyz",
            "status": "COMPLETED",
            "output": {"media_url": "https://cdn.higgsfield.ai/fake.mp4"},
        }
    ).encode()

    resp = await _post_higgsfield_webhook(body, _sign(secret, body))

    assert resp.status_code == 200
    assert resp.json() == {"received": True}


@pytest.mark.asyncio
async def test_webhook_invalid_signature_returns_403(test_asset) -> None:  # type: ignore[misc]
    """Request with wrong HMAC must be rejected before any DB access."""
    body = json.dumps(
        {"generation_id": test_asset["job_id"], "status": "COMPLETED", "output": {}}
    ).encode()

    resp = await _post_higgsfield_webhook(body, "sha256=badhash")

    assert resp.status_code == 403
