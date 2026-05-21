# Repository Guidelines

## Architecture Guardrails (Must Follow)
- Read `docs/adr/README.md` before structural changes.
- Keep layer boundaries strict:
  - `tools/` orchestrate input/output only.
  - `services/` hold business logic.
  - `services/providers/` is the only place for provider API calls.
  - `db/migrations/` must evolve schema and RLS together.
- Do not automate provider dashboards (ADR-0004).
- Paid/external actions require explicit approval and budget checks (ADR-0005).
- MCP outputs must be compact and structured (ADR-0011).

## Security Guardrails (Must Follow)
- Never commit secrets, tokens, cookies, private client data, or raw client assets.
- Use only environment variables for credentials (`.env.example` documents required keys).
- Redact sensitive fields in logs, errors, and tool outputs.
- Enforce auth/session context for authorization; never trust raw `client_id` input.
- For paid/external actions, require pre-approval, cost estimate, and audit trail.
- Treat RLS as mandatory isolation for client-scoped data.

## Project Structure
- `src/vos_studio_mcp/server.py`: FastMCP/FastAPI entrypoint.
- `src/vos_studio_mcp/tools/`: one file per MCP tool (`snake_case`).
- `src/vos_studio_mcp/schemas/`: Pydantic request/response models.
- `src/vos_studio_mcp/services/`: domain logic, storage, audit, cost.
- `src/vos_studio_mcp/tasks/`: Celery jobs.
- `tests/`: `tools/`, `services/`, `providers/`, `integration/`.
- `docs/adr/`: architecture source of truth.

## Commands
- `make sync`: install dependencies.
- `make dev`: run API locally.
- `make worker`: run Celery worker.
- `make flower`: run Flower monitoring.
- `make migrate`: apply Alembic migrations.
- `make lint && make typecheck`: static checks.
- `make test`: test suite with coverage.
- `make check`: run lint, typecheck, and tests.

## Conventions
- Python 3.12, 4-space indent, line length 100.
- Strong typing required (`mypy` strict).
- Naming:
  - files/functions/variables: `snake_case`
  - classes: `PascalCase`
  - constants/env vars: `UPPER_SNAKE_CASE`
- Errors must include stable `error_code`; logs should include `trace_id`.

## Engineering Principles
- `SOLID`: keep tools thin and service interfaces focused; depend on abstractions (provider adapter contract), not concrete providers.
- `YAGNI`: implement only what is required by the current milestone/ADR; avoid speculative endpoints, flags, and abstractions.
- `KISS`: prefer simple flow and explicit data contracts over clever indirection.
- `DRY`: centralize shared validation/error mapping; do not duplicate provider logic across tools.

## Clean Code Rules
- Functions should do one thing and stay small; split orchestration from transformation logic.
- Use explicit, domain-oriented names (`sprint_id`, `approval_token`, `estimated_cost`).
- Avoid magic values; extract constants/enums for statuses, modes, and error codes.
- Prefer early returns to reduce nested conditionals.
- Keep side effects at boundaries (I/O, DB, provider calls) and core logic deterministic.
- Write comments only when intent is not obvious from code.

## Testing Rules
- `pytest`, `pytest-asyncio`, `respx`, `pytest-cov`.
- Never call real provider APIs in tests.
- Every new tool needs:
  - unit test (`tests/tools/`)
  - MCP protocol test
- Every new client-scoped table needs integration + RLS isolation test.
- Security-sensitive paths (auth, approval, budget, RLS) require explicit negative tests.

## PR Requirements
- Use Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`).
- Small, focused PRs only.
- Include:
  - what changed and why,
  - linked issue/ADR (if architectural),
  - evidence: lint, typecheck, tests,
  - migration/RLS notes when schema changes,
  - security impact notes (threat, mitigation, residual risk) when relevant.
