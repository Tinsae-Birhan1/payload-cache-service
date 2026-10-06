# syntax=docker/dockerfile:1

# --- build: resolve dependencies with uv into a self-contained virtualenv ------------------
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Dependencies first, in their own layer: code changes do not invalidate the slow step.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# --- runtime: no build tooling, no uv, non-root -------------------------------------------
FROM python:3.12-slim-bookworm

RUN useradd --system --uid 10001 --no-create-home app

WORKDIR /app
COPY --from=builder --chown=app:app /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER app
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

# Migrations run before the server starts so the schema always matches the code.
# Fine for a single instance; with several replicas this would move to a one-off job.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn payload_cache.main:create_app --factory --host 0.0.0.0 --port 8000"]
