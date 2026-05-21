# VOS Studio MCP — Agent Guide

This file gives coding agents (Claude Code, Codex, and others) the context needed to work on this project safely and consistently.

## What this project is

VOS Studio MCP is a remote Model Context Protocol server that acts as the creative operations layer for VOS Studio, a performance creative agency. It orchestrates the full creative production workflow: client briefing → brand kit → creative sprint → prompt packs → generation → asset registration → QA → delivery.

It is **not** a generic image/video generator and **not** a dashboard automation tool. Read ADR-0003 and ADR-0004 before touching anything related to providers.

## Stack

| Layer | Tool |
|---|---|
| MCP server | `mcp` Python SDK — FastMCP |
| HTTP middleware | FastAPI + Uvicorn |
| Schema validation | Pydantic v2 |
| Database ORM | SQLAlchemy 2.0 async |
| Migrations | Alembic |
| Job queue | Celery + Redis |
| Package manager | `uv` |
| Linter / formatter | Ruff |
| Type checker | Mypy (strict) |

## Running locally

```bash
# Install dependencies
uv sync

# Copy and fill environment variables
cp .env.example .env

# Start Postgres and Redis (requires Docker)
docker compose up -d

# Apply database migrations
uv run migrate

# Start the MCP server
uv run dev

# Start the Celery worker (separate terminal)
uv run worker

# Monitor jobs (optional)
uv run flower
```

## Common commands

```bash
uv run test          # run all tests
uv run typecheck     # mypy strict check
uv run lint          # ruff check
uv run fmt           # ruff format
uv run makemig "description"  # generate a new Alembic migration
uv run migrate       # apply pending migrations
```

## Project structure

```
src/vos_studio_mcp/
  server.py           # FastMCP instance + FastAPI wrapper — entry point
  tools/              # one file per MCP tool, registered via @mcp.tool()
  schemas/            # Pydantic models for domain entities
  services/           # business logic — database, storage, audit, cost
  services/providers/ # provider adapters implementing ProviderAdapter Protocol
  tasks/              # Celery task definitions for long-running jobs
  config/env.py       # settings loaded from environment via pydantic-settings
db/
  models.py           # SQLAlchemy table definitions — single source of truth
  migrations/         # Alembic migration scripts
docs/adr/             # Architecture Decision Records — read before changing architecture
```

## How tools are defined

Every MCP tool lives in `src/vos_studio_mcp/tools/` and is registered with FastMCP via decorator. Tools are thin: validate input, call a service, return compact structured output.

```python
from mcp.server.fastmcp import FastMCP
from src.vos_studio_mcp.schemas.sprint import SprintInput, SprintResponse
from src.vos_studio_mcp.services import sprint_service

mcp: FastMCP  # imported from server.py

@mcp.tool()
async def create_creative_sprint(params: SprintInput) -> SprintResponse:
    """Create a new creative sprint for a client."""
    return await sprint_service.create(params)
```

Tool responses must follow the compact output convention (ADR-0011):

```python
{"status": "created", "sprint_id": "spr_123", "summary": "...", "next_action": "prepare_dashboard_pack"}
```

## How provider adapters work

All provider adapters implement the `ProviderAdapter` Protocol defined in `src/vos_studio_mcp/services/providers/base.py`. Tool handlers receive adapters via FastAPI dependency injection — they never import adapters directly.

Never call provider APIs directly from tool handlers. Always go through the adapter.

## Key rules (from ADRs)

- **Never automate provider dashboards** (ADR-0004). No Playwright, Selenium, or simulated clicks.
- **Never execute paid actions without budget pre-authorization** (ADR-0005). Always call `estimate_cost` before enqueuing a generation job.
- **Always return compact output from tools** (ADR-0011). Store details in the database; return references.
- **Always version prompts and presets** (ADR-0013). Every asset must record `prompt_version` and `preset_version`.
- **Never hardcode credentials** (ADR-0016). All secrets via environment variables.
- **Never commit `.env`** (ADR-0017). Only `.env.example` belongs in the repository.
- **RLS is the isolation layer** (ADR-0023). Never trust `client_id` from tool input for authorization — trust the session context.

## Architecture decisions

All architectural decisions are documented in `docs/adr/`. The index is at `docs/adr/README.md`.

Before making a structural change — new dependency, new pattern, new entity — check whether an ADR covers it. If not, create one before implementing.

## Testing

Tests live in `tests/`. Each tool has a unit test with mocked services. Integration tests use a real test database. Provider adapter tests mock HTTP responses with `respx`.

Never call real provider APIs in tests. Never write tests that depend on production credentials.

## Branch and PR workflow (ADR-0018)

- One branch per task. Branch name should describe the slice of work.
- Small, focused PRs. Avoid unrelated changes in the same PR.
- Reference the relevant ADR in the PR description when the change has architectural impact.
