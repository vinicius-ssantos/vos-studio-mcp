# ADR-0001 — Use Python as the primary language

Status: Amended  
Date: 2026-05-21  
Amended: 2026-05-21

## Context

VOS Studio MCP will be the operational server for VOS Studio's creative workflows. It needs to support MCP tools, schemas, authentication, provider integrations, storage, jobs, clients, brand kits, creative sprints, asset registration, QA, delivery workflows, and — in later milestones — performance data analysis to close the creative feedback loop (ADR-0025).

The project will also be developed with the help of coding agents such as Claude Code and Codex. The codebase should be typed, readable, modular, and easy for agents to navigate safely.

The original decision selected TypeScript. No code has been written yet. Before implementation begins, it is worth evaluating whether TypeScript is the right choice given the full stack requirements.

## Decision

Use **Python** with **FastAPI** and **Pydantic v2** as the primary language and framework.

Python was chosen over TypeScript after a direct comparison across every major component of the planned stack:

| Component | TypeScript option | Python option | Advantage |
|---|---|---|---|
| MCP SDK | `@modelcontextprotocol/sdk` | `mcp` (official) | Tied |
| HTTP framework | Fastify / Hono | FastAPI + Pydantic | Python |
| Schema validation | Zod | Pydantic v2 | Tied |
| ORM / migrations | Drizzle (new) | SQLAlchemy 2 + Alembic (15+ years) | Python |
| Job queue | Trigger.dev (2022) | Celery + Redis (battle-tested) | Python |
| HTTP client | axios / fetch | httpx async | Tied |
| Auth OAuth 2.1 | jose / passport | authlib | Tied |
| ML / image analysis (M6) | Minimal ecosystem | PyTorch, OpenCV, transformers | Python |
| Supabase client | `supabase-js` (first-class) | `supabase-py` (official) | TypeScript |

TypeScript had a genuine advantage only in the Supabase client. Python was equal or better in every other area. For the performance feedback loop (ADR-0025) and future ML-adjacent work in Milestone 6, Python's ecosystem is the clear winner.

The switch is being made before any code is written, so the migration cost is zero.

## Alternatives considered

- **TypeScript + Node.js**: original decision. Coherent stack but not the strongest option for this specific project. The planned tools (Drizzle, Trigger.dev) are TypeScript-only and would have locked the project into a weaker position for ML-adjacent work. Rejected in favor of Python before implementation began.
- **Go**: excellent HTTP performance and strong typing, but immature MCP SDK and weaker ML ecosystem. Rejected.
- **Rust**: strong performance guarantees, but too complex for a creative operations MVP developed with coding agents. Rejected.

## Consequences

The codebase uses Python 3.12+ with `uv` as the package manager. `uv` was chosen over `pip` and `poetry` for its speed, unified tooling (replaces pip + venv + pip-tools), and growing adoption as the modern Python standard.

Pydantic v2 provides schema validation from the boundary of every MCP tool input, equivalent to the role Zod played in the TypeScript plan. FastAPI consumes Pydantic models natively, keeping the validation layer consistent from HTTP to tool handler.

Python for auxiliary ML scripts (Milestone 6) is natural rather than a context switch — it is the same language and environment as the core server.

The main tradeoff is the Supabase JS client being slightly more feature-complete than `supabase-py`. This is acceptable because SQLAlchemy handles all database queries directly against Postgres, and the Supabase client is used only for auth and storage operations where `supabase-py` is sufficient.

## Impact on VOS Studio MCP

The project structure uses Python conventions:

```text
src/
  vos_studio_mcp/
    server.py
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

Package management uses `uv`. The `pyproject.toml` replaces `package.json`. There is no `tsconfig.json` or `node_modules/`.

MCP tools expose clear typed inputs via Pydantic models and compact structured outputs (ADR-0011). Agents navigate and modify the codebase predictably given Python's readability and the consistency of FastAPI + Pydantic conventions.
