# syntax=docker/dockerfile:1.4

FROM python:3.10-slim AS builder

WORKDIR /app

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

FROM python:3.10-slim

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.test \
    PORT=8080

LABEL maintainer="Medical AI Team" \
      description="Django Ninja Medical Web Application" \
      version="1.0"

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    libpq-dev \
    curl \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m appuser \
    && chown -R appuser:appuser /app

COPY --chown=appuser:appuser . .
RUN chmod +x /app/scripts/migrate.sh

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=60s --timeout=30s --start-period=10s --retries=2 \
    CMD curl -f http://localhost:8000/api/health/ || exit 1

ENTRYPOINT ["/app/scripts/migrate.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", "--timeout", "120", "--log-level", "debug", "--capture-output", "--access-logfile", "-", "--error-logfile", "-", "--enable-stdio-inheritance", "config.wsgi:application"]
