
# -- uv (Python env) --
# Install all dependencies (creates/updates .venv from uv.lock)
uv sync

# Add a package (example)
# uv add django

# -- Docker Compose --
docker compose build
docker compose up web db

./scripts/clear_db.sh

docker compose exec web python manage.py migrate

# docker compose web env

uv run python manage.py makemigrations

uv run python manage.py migrate

uv run python manage.py createsuperuser

uv run python manage.py runserver 0.0.0.0:8000

uv run python manage.py test
