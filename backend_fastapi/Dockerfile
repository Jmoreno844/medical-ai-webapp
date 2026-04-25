# syntax=docker/dockerfile:1.4

FROM python:3.14.4-slim AS builder

WORKDIR /app/backend_fastapi

COPY --from=ghcr.io/astral-sh/uv:0.11.2 /uv /usr/local/bin/uv

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    uv sync --frozen --no-dev

FROM python:3.14.4-slim

WORKDIR /app/backend_fastapi

COPY --from=builder /app/backend_fastapi/.venv /app/backend_fastapi/.venv

ENV PATH="/app/backend_fastapi/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update && apt-get install -y \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m appuser \
    && chown -R appuser:appuser /app/backend_fastapi

COPY --chown=appuser:appuser . ./

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=60s --timeout=30s --start-period=30s --retries=2 \
    CMD curl -f http://localhost:8080/api/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
