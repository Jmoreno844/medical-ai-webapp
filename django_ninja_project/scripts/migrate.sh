#!/bin/bash
set -e

echo "Migrate Using Django settings module: $DJANGO_SETTINGS_MODULE"

# Run migrations
python manage.py migrate

# Start gunicorn with the CMD arguments passed to the container
exec "$@"