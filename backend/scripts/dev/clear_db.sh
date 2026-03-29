#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=/dev/null
source "${BACKEND_ROOT}/.env"

echo "Using database credentials from .env file"
echo "Database: $DB_NAME, User: $DB_USER"

echo "Dropping and recreating the 'public' schema in the database..."

PGPASSWORD=$DB_PASSWORD psql -U "$DB_USER" -d "$DB_NAME" -h localhost <<EOF
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO public;
EOF

echo "Database tables have been deleted. You can now run your migrations."
echo "Run: python manage.py migrate"
