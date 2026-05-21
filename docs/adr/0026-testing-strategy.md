# ADR-0026 — Testing strategy

Status: Accepted  
Date: 2026-05-21

## Context

No testing approach has been defined for the project. For an MCP server with multiple layers — tool handlers, provider adapters, job queue, database with RLS, cost estimation, approval logic — the absence of a testing strategy means each developer or coding agent will invent their own approach. This leads to inconsistent coverage, tests that require real provider credentials, and RLS isolation bugs that only surface in production.

A testing strategy must be defined before the first tool is implemented (Milestone 1) so that all tools are built with testability in mind from the start.

The testing challenges specific to this project are:
- MCP tools cannot be tested with a standard HTTP client — they use the MCP protocol.
- Provider adapters call external APIs that must not be called in CI.
- RLS policies live in Postgres and cannot be tested without a real database.
- Celery tasks run asynchronously and must be testable synchronously in unit tests.

## Decision

Use a four-layer testing model:

### Layer 1 — Unit tests (tools and services)

Tool handlers and services are tested in isolation with all external dependencies mocked.

- **Framework**: `pytest` + `pytest-asyncio`
- **HTTP mocking**: `respx` for mocking `httpx` calls to provider APIs
- **Database mocking**: in-memory mock or `unittest.mock` for the database session
- **Celery tasks**: run synchronously using `task.apply()` with `CELERY_TASK_ALWAYS_EAGER=True` in test config

Each tool file in `src/vos_studio_mcp/tools/` must have a corresponding test file in `tests/tools/`. Each test covers: valid input → expected output, invalid input → validation error, service failure → tool error.

### Layer 2 — Integration tests (database and RLS)

Integration tests run against a real Postgres database. They verify that queries return correct data and that RLS policies correctly isolate client data.

- **Database**: a dedicated test database spun up via Docker Compose (`docker compose up postgres-test`)
- **Migrations**: `alembic upgrade head` applied to the test database before the test suite runs
- **Fixtures**: `pytest` fixtures create and tear down test clients, sprints, and assets per test
- **RLS tests**: every client-scoped table must have a test that proves a query authenticated as client A cannot return rows belonging to client B

Integration tests are marked with `@pytest.mark.integration` and excluded from the default `pytest` run. They run in CI on every PR but can be skipped locally with `pytest -m "not integration"`.

### Layer 3 — Adapter contract tests

Provider adapters are tested against the `ProviderAdapter` Protocol contract without calling real provider APIs.

- All HTTP calls are mocked with `respx` using realistic provider response payloads stored as JSON fixtures in `tests/fixtures/providers/`.
- Every adapter must pass the same contract test suite that verifies: `estimate_cost` never calls the provider API, `generate_image` raises `NotImplementedError` on manual adapters, `check_job_status` returns a valid `JobStatus`, etc.

### Layer 4 — MCP protocol tests

The FastMCP server is tested end-to-end using the MCP Python SDK's built-in test client, which exercises the full MCP protocol without needing a real HTTP connection.

```python
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client

async def test_create_sprint_tool():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            result = await session.call_tool("create_creative_sprint", {...})
            assert result.content[0].type == "text"
```

MCP protocol tests cover: tool is discoverable, input schema is correct, output matches the compact format (ADR-0011), error responses are well-formed.

## Alternatives considered

- **No testing strategy (ad hoc)**: every agent invents its own approach. Rejected — leads to untested RLS, real provider calls in CI, and no contract enforcement on adapters.
- **End-to-end only**: test only through the full stack. Rejected — too slow for CI and requires real credentials.
- **Unit tests only**: fast but misses RLS bugs and adapter contract violations. Rejected as the sole approach.
- **Four-layer model**: selected. Each layer tests a specific concern at the right level of isolation.

## Consequences

Every new tool added in Milestone 2+ must include Layer 1 and Layer 4 tests. Layer 2 RLS tests must be added for every new client-scoped table in Milestone 3+. Layer 3 contract tests must be added for every new provider adapter in Milestone 4+.

CI runs Layer 1 and Layer 4 on every commit. Layer 2 (integration) runs on every PR. Layer 3 (adapter contracts) runs on every PR when `src/vos_studio_mcp/services/providers/` is modified.

## Impact on VOS Studio MCP

- Add `pytest`, `pytest-asyncio`, `pytest-cov`, `respx` to dev dependencies in `pyproject.toml`.
- Create `tests/` directory with `tests/tools/`, `tests/services/`, `tests/providers/`, `tests/integration/`.
- Create `tests/fixtures/providers/` for JSON response payloads per provider.
- Create `tests/conftest.py` with database session fixtures and test client setup.
- Add `CELERY_TASK_ALWAYS_EAGER=True` and `DATABASE_URL` pointing to test DB in `pytest` configuration.
- Never use real provider API keys in any test. CI must not have provider credentials.
