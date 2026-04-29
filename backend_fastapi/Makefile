.PHONY: db-up db-migrate db-ready

DB_CONTAINER ?= medical-web-app-db
DB_NAME ?= medical_web_app
DB_USER ?= juan
DB_PASSWORD ?= 12345
DB_PORT ?= 5433
POSTGRES_IMAGE ?= postgres:15

db-up:
	@if docker ps --format '{{.Names}}' | grep -qx '$(DB_CONTAINER)'; then \
		echo 'PostgreSQL container $(DB_CONTAINER) is already running on port $(DB_PORT).'; \
	elif docker ps -a --format '{{.Names}}' | grep -qx '$(DB_CONTAINER)'; then \
		echo 'Starting existing PostgreSQL container $(DB_CONTAINER)...'; \
		docker start $(DB_CONTAINER); \
	else \
		echo 'Creating PostgreSQL container $(DB_CONTAINER) on port $(DB_PORT)...'; \
		docker run --name $(DB_CONTAINER) \
			-e POSTGRES_DB=$(DB_NAME) \
			-e POSTGRES_USER=$(DB_USER) \
			-e POSTGRES_PASSWORD=$(DB_PASSWORD) \
			-p $(DB_PORT):$(DB_PORT) \
			-d $(POSTGRES_IMAGE) -c port=$(DB_PORT); \
	fi

db-migrate:
	uv run alembic upgrade head

db-ready: db-up db-migrate