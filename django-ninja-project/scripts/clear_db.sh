#!/bin/bash
set -e

# Load environment variables from .env file
source /home/juan/Desktop/code/Proyecto_AI_Medico/github_medical_web_app/django_ninja_project/.env

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