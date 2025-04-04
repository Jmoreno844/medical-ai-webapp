#!/bin/bash
set -e

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log "Starting database connection setup..."

# Ensure DJANGO_SETTINGS_MODULE is properly set
if [ -z "$DJANGO_SETTINGS_MODULE" ]; then
  export DJANGO_SETTINGS_MODULE="config.settings.test"
  log "DJANGO_SETTINGS_MODULE not set, defaulting to $DJANGO_SETTINGS_MODULE"
else
  log "Using DJANGO_SETTINGS_MODULE: $DJANGO_SETTINGS_MODULE"
fi

# Verify PORT environment variable is set
log "Using PORT: ${PORT:-8080}"

# Try to get values from Secret Manager, fall back to env vars
if command -v gcloud &> /dev/null; then
  log "Using Google Cloud Secret Manager to retrieve database connection details"
  
  # Get database credentials from Secret Manager
  # Note: Using the secret names as they appear in your Secret Manager
  POSTGRES_HOST=${POSTGRES_HOST:-$(gcloud secrets versions access latest --secret="db_host" 2>/dev/null || echo "localhost")}
  POSTGRES_PORT=${POSTGRES_PORT:-$(gcloud secrets versions access latest --secret="POSTGRES_PORT" 2>/dev/null || echo "5432")}
  POSTGRES_DB=${POSTGRES_DB:-$(gcloud secrets versions access latest --secret="db_name" 2>/dev/null || echo "postgres")}
  POSTGRES_USER=${POSTGRES_USER:-$(gcloud secrets versions access latest --secret="db_user" 2>/dev/null || echo "postgres")}
  POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-$(gcloud secrets versions access latest --secret="db_password" 2>/dev/null || echo "")}
  
  # Export these variables so Django can use them
  export POSTGRES_HOST
  export POSTGRES_PORT
  export POSTGRES_DB
  export POSTGRES_USER
  export POSTGRES_PASSWORD
else
  log "Using environment variables for database connection details"
  # Ensure all required variables have defaults
  POSTGRES_HOST=${POSTGRES_HOST:-localhost}
  POSTGRES_PORT=${POSTGRES_PORT:-5432}
  POSTGRES_DB=${POSTGRES_DB:-postgres}
  POSTGRES_USER=${POSTGRES_USER:-postgres}
  POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-""}
fi

# Log connection details (but don't show sensitive information in production logs)
if [ "$DJANGO_SETTINGS_MODULE" = "config.settings.production" ]; then
  log "Connecting to PostgreSQL database $POSTGRES_DB on port $POSTGRES_PORT (host and credentials masked for security)"
else
  log "Connecting to PostgreSQL database $POSTGRES_DB at $POSTGRES_HOST:$POSTGRES_PORT with user $POSTGRES_USER"
fi

# Check if netcat is available
if ! command -v nc &> /dev/null; then
  log "WARNING: netcat not found, skipping database connection check"
else
  log "Waiting for PostgreSQL to be available..."
  MAX_RETRIES=10
  RETRY_COUNT=0

  while ! nc -z $POSTGRES_HOST $POSTGRES_PORT; do
    RETRY_COUNT=$((RETRY_COUNT+1))
    if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
      log "WARNING: Failed to connect to PostgreSQL after $MAX_RETRIES attempts, continuing anyway"
      break
    fi
    log "Attempt $RETRY_COUNT/$MAX_RETRIES: PostgreSQL not available yet, retrying in 1 second..."
    sleep 1
  done
  
  if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
    log "Successfully connected to PostgreSQL"
  fi
fi

# Try to run migrations but don't fail if they don't succeed
log "Running database migrations..."
python manage.py migrate || log "WARNING: Migrations failed but continuing startup"

log "Checking for superuser..."
python manage.py create_superuser || log "WARNING: Issue with superuser creation, but continuing anyway"

log "Starting application..."
log "Command to execute: $@"
exec "$@"