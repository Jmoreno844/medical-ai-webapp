#!/bin/bash
set -e

echo "Dropping and recreating the 'public' schema in the database..."

docker compose exec db psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} <<EOF
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
EOF

echo "Database tables have been deleted. You can now run your migrations."