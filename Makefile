.PHONY: sync dev worker flower migrate makemig lint fmt typecheck test check

sync:
	uv sync --dev

dev:
	uv run uvicorn vos_studio_mcp.server:app --reload --port 8000

worker:
	uv run celery -A vos_studio_mcp.tasks.celery_app worker --loglevel=info

flower:
	uv run celery -A vos_studio_mcp.tasks.celery_app flower --port=5555

migrate:
	uv run alembic upgrade head

makemig:
	uv run alembic revision --autogenerate -m "$(m)"

lint:
	uv run ruff check src/ tests/

fmt:
	uv run ruff format src/ tests/

typecheck:
	uv run mypy src/

test:
	uv run pytest

check: lint typecheck test
