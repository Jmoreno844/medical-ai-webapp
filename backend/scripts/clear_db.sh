#!/bin/bash
set -e

# Load environment variables from .env next to manage.py (backend root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../.env"

echo "Using database credentials from .env file"
echo "Database: $DB_NAME, User: $DB_USER"

echo "Dropping and recreating the 'public' schema in the database..."

# Connect directly with psql using .env variables
PGPASSWORD=$DB_PASSWORD psql -U $DB_USER -d $DB_NAME -h localhost <<EOF
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO public;
EOF

echo "Database tables have been deleted. You can now run your migrations."
echo "Run: python manage.py migrate"