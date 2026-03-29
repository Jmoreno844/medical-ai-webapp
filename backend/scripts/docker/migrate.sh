#!/bin/bash
set -e

echo "Migrate using Django settings module: ${DJANGO_SETTINGS_MODULE:-unset}"

python manage.py migrate

exec "$@"
