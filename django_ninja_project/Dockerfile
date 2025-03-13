FROM python:3.10-slim AS builder

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install poetry
RUN pip install poetry==1.7.1

# Copy poetry files
COPY pyproject.toml poetry.lock* ./

# Explicitly remove psycopg2 and add psycopg2-binary
RUN poetry config virtualenvs.create false \
    && poetry remove psycopg2 --quiet || true \
    && poetry add psycopg2-binary \
    && poetry export -f requirements.txt > requirements.txt

# Final stage
FROM python:3.10-slim

WORKDIR /app

# Add metadata labels
LABEL maintainer="Medical AI Team"
LABEL description="Django Ninja Medical Web Application"
LABEL version="1.0"

# Install system dependencies including gcc for building packages
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m appuser && \
    chown -R appuser:appuser /app

# Copy requirements from builder stage
COPY --from=builder /app/requirements.txt .

# Install dependencies with additional error handling
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install gunicorn

# Copy project files
COPY --chown=appuser:appuser . .

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health/ || exit 1

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production

# Run the application with Gunicorn
ENTRYPOINT ["gunicorn"]
CMD ["--bind", "0.0.0.0:8080", "--workers", "3", "config.wsgi:application"]
