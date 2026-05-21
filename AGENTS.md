# Repository Guidelines

## Project Structure & Module Organization
This repository is in early implementation stage, with architecture defined in docs first.

- `docs/adr/`: Architecture Decision Records (source of truth for structural decisions).
- `src/vos_studio_mcp/`: main Python package (FastMCP/FastAPI server, tools, services, tasks).
- `tests/`: automated tests (unit, integration, provider contracts, MCP protocol).
- `db/migrations/`: Alembic migrations.
- `.env.example`: required environment variables template.

Before changing architecture, read [docs/adr/README.md](/C:/Users/vinicius/Documents/workspace/vos-studio-mcp/docs/adr/README.md).

## Build, Test, and Development Commands
Use `uv` for dependency and task management.

- `uv sync --dev`: install runtime + dev dependencies.
- `uv run dev`: run local API server with reload on `:8000`.
- `uv run worker`: start Celery worker.
- `uv run flower`: open Celery monitoring UI on `:5555`.
- `uv run migrate`: apply DB migrations.
- `uv run makemig -- -m "add_new_table"`: create migration.
- `uv run lint`: run Ruff lint checks.
- `uv run fmt`: format code with Ruff.
- `uv run typecheck`: run strict MyPy checks.
- `uv run test`: run pytest with coverage.

## Coding Style & Naming Conventions
- Python 3.12, 4-space indentation, max line length 100.
- Type hints are required (`mypy` is `strict = true`).
- Keep MCP tool outputs compact and structured (see ADR-0011).
- Naming:
  - modules/files: `snake_case.py`
  - functions/variables: `snake_case`
  - classes/Pydantic models: `PascalCase`
  - constants/env vars: `UPPER_SNAKE_CASE`

## Testing Guidelines
- Framework: `pytest` + `pytest-asyncio` + `pytest-cov`.
- Provider HTTP interactions must be mocked (use `respx`).
- Test layout:
  - `tests/tools/` for tool handlers
  - `tests/services/` for business services
  - `tests/providers/` for adapter contract tests
  - `tests/integration/` for DB/RLS integration tests
- Name tests `test_<feature>.py` and functions `test_<behavior>()`.

## Commit & Pull Request Guidelines
Follow Conventional Commit style seen in history:
- `feat: ...`
- `docs: ...`
- `chore: ...`

PRs should be small and focused, include:
- clear summary of behavior change,
- linked issue/ADR when relevant,
- test evidence (`uv run test`, lint/typecheck status),
- migration notes for schema changes.

## Security & Configuration Tips
- Never commit real credentials, tokens, cookies, or client assets.
- Keep secrets in environment variables only.
- Redact sensitive data from logs and tool responses.
