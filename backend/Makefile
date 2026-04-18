# Local dev shortcuts (uv). Run from backend/: `make help`
# Or from repo root: `make -C backend help`

ifeq ($(wildcard manage.py),)
$(error Run make from backend/, or: make -C backend <target>)
endif

UV := uv
PY := $(UV) run python

.DEFAULT_GOAL := help

.PHONY: help sync sync-frozen sync-dev sync-dev-frozen install run runserver migrate \
	makemigrations test pytest shell createsuperuser lint format check pre-commit \
	pre-commit-all clear-db db-up db-down up-db down-db

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
