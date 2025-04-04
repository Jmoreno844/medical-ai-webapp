# Enable BuildKit features
# syntax=docker/dockerfile:1.4

FROM python:3.10-slim AS builder

WORKDIR /app

# Install system dependencies - combine RUN commands to reduce layers
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install poetry
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install poetry==1.7.1

# Copy only dependency files first to leverage Docker layer caching
COPY pyproject.toml poetry.lock* ./

# Generate requirements.txt
RUN --mount=type=cache,target=/root/.cache/pypoetry,sharing=locked \
    poetry config virtualenvs.create false \
    && poetry remove psycopg2 --quiet || true \
    && poetry add psycopg2-binary \
    && poetry add gunicorn \
    && poetry export -f requirements.txt > requirements.txt

# Final stage
FROM python:3.10-slim

WORKDIR /app

# Add metadata labels
LABEL maintainer="Medical AI Team" \
      description="Django Ninja Medical Web Application" \
      version="1.0"

# Install system dependencies - combine into one layer
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

# Copy requirements from builder stage
COPY --from=builder /app/requirements.txt .

# Install dependencies with pip cache
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy project files and set permissions in one layer
COPY --chown=appuser:appuser . .
RUN chmod +x /app/scripts/run-migrations.sh

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=60s --timeout=30s --start-period=10s --retries=2 \
    CMD curl -f http://localhost:8000/api/health/ || exit 1

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.test \
    PORT=8080

# Use our script as entrypoint
ENTRYPOINT ["/app/scripts/run-migrations.sh"]

# Command
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", "--timeout", "120", "--log-level", "debug", "--capture-output", "--access-logfile", "-", "--error-logfile", "-", "--enable-stdio-inheritance", "config.wsgi:application"]