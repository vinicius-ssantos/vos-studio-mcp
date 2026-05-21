# ADR-0020 — Database schema evolution and migration strategy

Status: Amended  
Date: 2026-05-21  
Amended: 2026-05-21

## Context

ADR-0007 decided that Postgres via Supabase will be the system of record. ADR-0013 requires that prompts and presets be versioned, and every generated asset must record which prompt and preset version produced it.

As the system evolves — new providers (ADR-0009), new sprint fields (ADR-0010), new budget controls (ADR-0012), new audit events (ADR-0015) — the database schema will change frequently. Without an explicit migration strategy, schema drift, broken deployments, and data loss become likely.

The original decision selected Drizzle ORM because it aligns with TypeScript (ADR-0001 original). With the switch to Python (ADR-0001 amended), Drizzle is no longer applicable. A Python-native solution is required.

## Decision

Use **SQLAlchemy 2.0** (async) as the ORM and **Alembic** as the migration tool.

SQLAlchemy + Alembic was chosen because:
- It is the most mature and battle-tested ORM stack in the Python ecosystem, with over 15 years of production use.
- Alembic generates versioned migration scripts that are reviewed in Git before being applied — the same workflow principle as the previous Drizzle decision.
- SQLAlchemy 2.0's async API (`asyncpg` driver) is fully compatible with FastAPI's async request handling (ADR-0001).
- Alembic integrates natively with SQLAlchemy models, so schema definitions and migration generation stay in sync automatically.
- Both tools have extensive documentation and strong community knowledge, reducing risk for agent-assisted development.

Migration scripts live in `db/migrations/versions/`. Each migration has an Alembic-generated revision ID and a descriptive name (e.g. `0001_create_clients.py`).

All schema changes must go through an Alembic migration script. No schema changes via the Supabase dashboard UI in production.

## Alternatives considered

- **Drizzle ORM**: TypeScript-only. Not applicable after ADR-0001 amendment. Rejected.
- **Django ORM**: mature and batteries-included, but Django's full framework is unnecessary overhead for a FastAPI server. Rejected.
- **Tortoise ORM**: async-native Python ORM, but significantly less mature than SQLAlchemy and smaller community. Rejected.
- **Raw SQL with Alembic only**: gives maximum control but requires writing all queries manually. Acceptable for a future performance-critical path, not for the initial implementation. Rejected as the primary approach.
- **Supabase dashboard UI**: suitable for exploration, not for repeatable production deployments. Rejected for production use.

## Consequences

All schema changes are code-reviewed via PRs before they are applied. Alembic's `--autogenerate` flag compares the current SQLAlchemy models against the live database and generates the migration diff automatically, reducing manual migration authoring.

Migration scripts, once merged and applied to production, must not be modified — only new migrations can alter the schema.

SQLAlchemy models in `db/models.py` become the single source of truth for table structure. Pydantic schemas in `src/vos_studio_mcp/schemas/` are derived from or validated against these models, keeping the type system consistent from database to MCP tool output.

## Impact on VOS Studio MCP

- Add `sqlalchemy[asyncio]`, `alembic`, and `asyncpg` to `pyproject.toml` in Milestone 3.
- Create `db/models.py` as the single source of truth for SQLAlchemy table definitions.
- Create `db/migrations/` with Alembic's standard directory structure (`env.py`, `versions/`).
- Add a `db:migrate` script to `pyproject.toml` scripts (e.g. `uv run alembic upgrade head`) for applying migrations in CI and deployment.
- The `.env.example` must include the `DATABASE_URL` variable for the Supabase Postgres connection string (format: `postgresql+asyncpg://...`).
- Local development uses the same Postgres schema via a local Supabase instance or a Docker Postgres container.
- RLS policies (ADR-0023) are applied as raw SQL within Alembic migration scripts using `op.execute()`.
