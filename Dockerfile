# =============================================================================
# VOS Studio MCP — Multi-stage Dockerfile
# Stage 1: builder (installs deps with uv)
# Stage 2: runtime (lean image, no dev tools)
# =============================================================================

# ---------- Stage 1: builder --------------------------------------------------
FROM python:3.12-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency manifests first (layer cache)
COPY pyproject.toml uv.lock ./

# Install production deps only into /app/.venv
RUN uv sync --frozen --no-dev --no-install-project

# Copy application source
COPY src/ ./src/
COPY db/ ./db/
COPY alembic.ini ./

# Install the project itself
RUN uv sync --frozen --no-dev

# ---------- Stage 2: runtime --------------------------------------------------
FROM python:3.12-slim AS runtime

# Non-root user for security
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --shell /bin/sh --create-home appuser

WORKDIR /app

# Copy only the installed environment and source from builder
COPY --from=builder --chown=appuser:appgroup /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appgroup /app/src /app/src
COPY --from=builder --chown=appuser:appgroup /app/db /app/db
COPY --from=builder --chown=appuser:appgroup /app/alembic.ini /app/alembic.ini

# Activate venv
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

USER appuser

EXPOSE 8000

# Default: run the web server.
# PORT env var is injected by Railway/Render; falls back to 8000 for local/Docker Compose.
# Override CMD to run the Celery worker (see docker-compose.yml).
CMD ["sh", "-c", "uvicorn vos_studio_mcp.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
