
# -- Poetry commands --
# Install all dependencies
poetry install
poetry check

# Add a package (example: django)
# poetry add django

# -- Docker Compose commands --
# Rebuild Docker images (use --no-cache if needed)
docker compose build

# Bring up only the web and db services (excluding tests)
docker compose up web db

./scripts/clear_db.sh

docker compose exec web python manage.py migrate
# Bring up all services (if needed)
docker compose web env
# docker-compose up

poetry run python manage.py makemigrations

poetry run python manage.py migrate

# Create a superuser (for admin access)
poetry run python manage.py createsuperuser

# Run the development server
poetry run python manage.py runserver 0.0.0.0:8000

# Run Django tests
poetry run python manage.py test

