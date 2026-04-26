# Local dev shortcuts (uv). Run from backend/: `make help`
# Or from repo root: `make -C backend help`

ifeq ($(wildcard manage.py),)
$(error Run make from backend/, or: make -C backend <target>)
endif

UV := uv
PY := $(UV) run python

.DEFAULT_GOAL := help

.PHONY: help sync sync-frozen sync-dev sync-dev-frozen install run runserver fastapi-run \
	fastapi-check fastapi-docker-build fastapi-compose-up migrate makemigrations test pytest shell \
	createsuperuser lint format check pre-commit pre-commit-all clear-db db-up \
	db-down up-db down-db

help: ## Show available targets
	@echo "Backend (uv) — run from backend/"
	@grep -E '^[a-zA-Z0-9_.-]+:.*?##' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

sync: ## uv sync (runtime deps only)
	$(UV) sync

sync-dev: ## uv sync + dev group (pytest, ruff, black, pre-commit)
	$(UV) sync --group dev

install: sync-dev ## alias: same recipe as sync-dev

sync-frozen: ## uv sync --frozen (CI-style, fails if lock drifts)
	$(UV) sync --frozen

sync-dev-frozen: ## frozen sync including dev group
	$(UV) sync --frozen --group dev

runserver: ## Django runserver 0.0.0.0:8001
	$(PY) manage.py runserver 0.0.0.0:8001

run: runserver ## alias: same as runserver

fastapi-run: ## FastAPI migration app on 0.0.0.0:8002
	cd ../backend_fastapi && $(UV) run uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload

fastapi-check: ## FastAPI migration tests
	cd ../backend_fastapi && $(UV) run pytest -q

fastapi-docker-build: ## Build the parallel FastAPI image from repo root context
	cd ../backend_fastapi && docker build -t medical-fastapi-migration:local .

fastapi-compose-up: ## docker compose: db + web_fastapi (profile fastapi; migrate Django once on fresh DB first)
	docker compose --profile fastapi up -d --build web_fastapi db

migrate: ## apply migrations
	$(PY) manage.py migrate

makemigrations: ## create migration files
	$(PY) manage.py makemigrations

test: ## pytest (pytest.ini / config.settings.test)
	$(UV) run pytest

pytest: test ## alias: same as test

shell: ## Django shell
	$(PY) manage.py shell

createsuperuser: ## Django createsuperuser
	$(PY) manage.py createsuperuser

lint: ## ruff check
	$(UV) run ruff check .

format: ## ruff format + black
	$(UV) run ruff format .
	$(UV) run black .

check: ## ruff check + pytest -q (quick local gate)
	$(UV) run ruff check .
	$(UV) run pytest -q

pre-commit: ## pre-commit on staged files
	$(UV) run pre-commit run

pre-commit-all: ## pre-commit on entire tree (slow)
	$(UV) run pre-commit run --all-files

clear-db: ## drop public schema (needs .env + local Postgres)
	bash scripts/dev/clear_db.sh

db-up: ## docker compose: start Postgres (`db` service) in background
	docker compose up -d db

up-db: db-up ## alias for db-up

db-down: ## docker compose: stop Postgres (volume kept)
	docker compose stop db

down-db: db-down ## alias for db-down
