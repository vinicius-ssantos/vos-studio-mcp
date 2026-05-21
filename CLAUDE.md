# VOS Studio MCP - Agent Playbook

Use this file as the implementation playbook for coding agents.

## 1) Architecture First
- ADRs in `docs/adr/` are binding decisions.
- If a change introduces a new architectural pattern, dependency, or cross-cutting behavior, create/amend an ADR before implementation.
- Respect this flow:
  - Request -> FastAPI middleware -> FastMCP tool -> service -> provider/storage/db

## 2) Layer Boundaries
- `tools/`: validate input, call services, return compact response.
- `services/`: business rules and orchestration.
- `services/providers/`: adapter implementations and provider-specific translation.
- `tasks/`: long-running async work only.
- Forbidden:
  - direct provider calls from `tools/`
  - business logic in route/tool wiring
  - schema changes without migration + RLS updates

## 3) Required Conventions
- Python 3.12, strict typing, `ruff` + `mypy`.
- Tool response shape should be short and predictable:
  - `status`, `summary`, entity IDs, `next_action` when relevant.
- Error contract:
  - normalized `error_code`
  - safe message for tool output
  - structured logs with `trace_id`, `tool_name`, optional `job_id`

## 4) Security and Engineering Principles
- Security defaults:
  - deny-by-default on authorization paths
  - never trust caller-provided `client_id` for access control
  - never expose secrets or provider raw payloads in outputs/logs
- `SOLID`: one responsibility per module; program to provider contracts.
- `YAGNI`: do not add abstractions/features without current milestone need.
- `KISS`: choose straightforward control flow and explicit schemas.
- `DRY`: reuse shared validators, error mappers, and response builders.

## 5) Clean Code Expectations
- Small cohesive functions, no hidden side effects.
- Prefer descriptive names over comments.
- Replace magic strings with enums/constants.
- Keep branching shallow with guard clauses.
- Keep tools as orchestration-only; move logic to services.

## 6) Implementation Checklists
### New MCP tool
1. Add schema models in `schemas/`.
2. Add thin tool in `tools/`.
3. Add service logic in `services/`.
4. Add unit test + MCP protocol test.
5. Confirm output follows ADR-0011.

### New provider adapter
1. Implement `ProviderAdapter` contract.
2. Add/extend contract tests in `tests/providers/`.
3. Map provider errors to normalized `error_code`.
4. Ensure no secret leakage in logs.

### Database change
1. Create Alembic migration.
2. Add/adjust RLS policies in same migration set.
3. Add integration tests for isolation (`client A` cannot read `client B`).

## 7) Security and Cost Controls
- Never automate provider dashboards (ADR-0004).
- Never execute paid actions without pre-approval/budget checks (ADR-0005).
- Never commit credentials, tokens, cookies, or client assets.

## 8) Delivery Standard (Definition of Done)
A change is done only when:
- architecture is ADR-compliant,
- lint/typecheck/tests pass,
- migrations + RLS + tests are included (if schema changed),
- docs are updated when conventions or behavior changed.
