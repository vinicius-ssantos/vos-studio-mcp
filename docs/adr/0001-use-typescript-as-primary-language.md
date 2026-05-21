# ADR-0001 — Use Python as the primary language

Status: Amended  
Date: 2026-05-21  
Amended: 2026-05-21

## Context

VOS Studio MCP will be the operational server for VOS Studio's creative workflows. It needs to support MCP tools, schemas, authentication, provider integrations, storage, jobs, clients, brand kits, creative sprints, asset registration, QA, delivery workflows, and — in later milestones — performance data analysis to close the creative feedback loop (ADR-0025).

The project will also be developed with the help of coding agents such as Claude Code and Codex. The codebase should be typed, readable, modular, and easy for agents to navigate safely.

The original decision selected TypeScript. No code has been written yet, so the switch to Python carries zero migration cost.

## Decision

Use **Python 3.12+** as the primary language with the following core framework stack:

- **`mcp` (official Python SDK) + FastMCP** — MCP server and tool definitions
- **FastAPI + Starlette** — HTTP middleware layer (auth, rate limiting)
- **Pydantic v2** — schema validation for tool inputs and domain models
- **`uv`** — package management

### FastMCP as the MCP layer

FastMCP is the high-level API provided by the official `mcp` Python SDK. It is the correct way to build MCP servers in Python — it handles the MCP protocol (JSON-RPC, schema generation, transport) so the codebase only defines business logic.

Tools are defined with a decorator:

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("VOS Studio MCP")

@mcp.tool()
async def create_creative_sprint(
    client_id: str,
    brief: str,
    budget_usd: float,
) -> dict:
    """Create a new creative sprint for a client."""
    ...
```

Python type hints on function signatures become the tool's input schema automatically. Pydantic models can be used as parameter types for complex inputs, keeping validation consistent across the stack.

### FastAPI as the HTTP middleware layer

FastMCP exposes the MCP server as an ASGI application. FastAPI wraps it to add:

- OAuth 2.1 authentication middleware (ADR-0019)
- Rate limiting
- Health check endpoints
- Any future HTTP concerns that are not part of the MCP protocol

```
Request
  → FastAPI middleware (auth, rate limiting)
  → FastMCP ASGI app (MCP protocol, tool dispatch)
  → tool handler (business logic)
  → services (database, providers, storage)
```

FastMCP supports both HTTP (Streamable HTTP / SSE) and stdio transports from the same codebase. stdio is used for local development and testing; HTTP is used for the remote production server (ADR-0002).

### Why Python over TypeScript

| Component | TypeScript option | Python option | Advantage |
|---|---|---|---|
| MCP SDK | `@modelcontextprotocol/sdk` | `mcp` + FastMCP (official) | Python |
| MCP tool definition | Manual schema + handler wiring | `@mcp.tool()` decorator | Python |
| HTTP framework | Fastify / Hono | FastAPI + Pydantic | Python |
| Schema validation | Zod | Pydantic v2 | Tied |
| ORM / migrations | Drizzle (new) | SQLAlchemy 2 + Alembic (15+ years) | Python |
| Job queue | Trigger.dev (2022) | Celery + Redis (battle-tested) | Python |
| HTTP client | axios / fetch | httpx async | Tied |
| Auth OAuth 2.1 | jose / passport | authlib | Tied |
| ML / image analysis (M6) | Minimal ecosystem | PyTorch, OpenCV, transformers | Python |
| Supabase client | `supabase-js` (first-class) | `supabase-py` (official) | TypeScript |

TypeScript had a genuine advantage only in the Supabase client. Python is equal or better in every other area. FastMCP specifically makes Python the stronger choice for the MCP layer itself, reversing the earlier "tied" assessment for the SDK column.

## Alternatives considered

- **TypeScript + Node.js**: original decision. Coherent stack but not the strongest option for this project. The planned tools (Drizzle, Trigger.dev) are TypeScript-only and lock the project into a weaker position for ML-adjacent work and for the MCP tool definition experience. Rejected before implementation began.
- **FastAPI without FastMCP**: using FastAPI to implement the MCP protocol manually. More control but significant boilerplate and risk of protocol drift. Rejected — the official SDK handles this correctly.
- **Go**: excellent HTTP performance and strong typing, but immature MCP SDK and weaker ML ecosystem. Rejected.
- **Rust**: strong performance guarantees, but too complex for a creative operations MVP developed with coding agents. Rejected.

## Consequences

The codebase uses Python 3.12+ with `uv` as the package manager. `uv` replaces pip + venv + pip-tools with a single fast tool. The `pyproject.toml` replaces `package.json`. There is no `tsconfig.json` or `node_modules/`.

Tool definitions in `src/vos_studio_mcp/tools/` are thin: they register with FastMCP via decorator, validate input with Pydantic, delegate to services, and return compact structured output (ADR-0011). The MCP protocol layer is invisible to tool authors.

Pydantic v2 is the single validation library across tool inputs, domain schemas, and SQLAlchemy model serialization. No secondary validation library is needed.

Python for auxiliary ML scripts (Milestone 6) is natural — same language, same environment, same dependency management.

The main tradeoff is the Supabase JS client being slightly more feature-complete than `supabase-py`. This is acceptable because SQLAlchemy handles all database queries directly, and `supabase-py` is only used for auth and storage where it is sufficient.

## Impact on VOS Studio MCP

```text
src/
  vos_studio_mcp/
    server.py           ← FastMCP instance + FastAPI wrapper
    tools/
      create_client.py
      save_brand_kit.py
      create_creative_sprint.py
      prepare_dashboard_pack.py
      estimate_generation_cost.py
      register_manual_asset.py
      review_asset_quality.py
      create_delivery_pack.py
      record_performance.py
    schemas/
      client.py
      brand_kit.py
      sprint.py
      asset.py
      job.py
      approval.py
      performance.py
    services/
      database.py
      storage.py
      audit_log.py
      cost_estimator.py
      providers/
        base.py
        manual_dashboard.py
        higgsfield.py
        freepik.py
        magnific.py
    tasks/
      generation.py
    config/
      env.py
db/
  models.py
  migrations/
pyproject.toml
.env.example
```

Key dependencies: `mcp`, `fastapi`, `pydantic`, `sqlalchemy[asyncio]`, `alembic`, `asyncpg`, `celery[redis]`, `httpx`, `authlib`, `supabase`.
