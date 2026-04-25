# FastAPI Backend Migration App

This service is the parallel FastAPI implementation used to migrate the
existing Django backend incrementally. Django remains the production source of
truth until every clinical contract has been ported and verified.

Current runtime baseline:

- Python `3.14.x` locally, Docker pinned to `3.14.4`
- FastAPI `0.136.1`

## Local commands

```bash
uv sync --group dev
uv run alembic upgrade head
ENVIRONMENT=local uv run uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
uv run pytest -q
```

FastAPI listens on `http://localhost:8001` with the command above. The first public route is
`GET /api/v1/health`.

Docker build:

```bash
docker build -t medical-fastapi-migration:local .
```

From the repo root, use `--project`:

```bash
ENVIRONMENT=local uv --project backend_fastapi run uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

Use `8001` only when Django is stopped.

## Current constraints

- Redis is intentionally out of scope for the first migration phase.
- SSE uses an in-memory hub equivalent to the Django implementation.
- Cloud Run must stay at `max-instances=1` with session affinity while SSE is
  backed by process memory.
- New endpoints live under `/api/v1`; legacy `/api/*` compatibility is temporary
  and should not receive new product features.
- When porting Django modules, preserve useful comments that explain contracts,
  security assumptions, legacy compatibility or clinical constraints.

## App layout

FastAPI code is organized by clinical domain:

- `app/domains/auth/` — browser JWT cookies, CSRF-aware auth helpers, user profile.
- `app/domains/encounters/` — encounter CRUD and audio metadata/upload URL routes.
- `app/domains/documents/` — document CRUD, editor content sync, SSE token/stream hub.
- `app/domains/patients/` — doctor-scoped patient create/update/search.
- `app/domains/templates/` — doctor template CRUD and usage tracking.
- `app/domains/system/` — health and CSRF routes.

`app/api/v1/router.py` only composes domain routers under `/api/v1`; new product
behavior should live in the domain folder that owns it.

## Settings and auth state

FastAPI selects typed settings from `ENVIRONMENT`:

- `local`, `dev`, `development` — local defaults, `../backend/.env`,
  `backend_fastapi/.env`, then `backend_fastapi/.env.local`.
- `test`, `ci` — test-safe defaults and optional `backend_fastapi/.env.test`.
- `stg`, `staging` — production-like validation and optional
  `backend_fastapi/.env.stg`.
- `prod`, `production` — production validation from real environment variables.

`app/core/config.py` remains the compatibility import for `Settings` and
`get_settings()`, while the environment-specific classes live under
`app/core/settings/`. In staging and production, FastAPI fails startup if
`JWT_SECRET_KEY`, database config, CORS origins, `GCP_PROJECT_ID`, or
`GCS_BUCKET_NAME` are missing.

`DATABASE_URL` takes precedence over `DB_NAME` / `DB_USER` / `DB_PASSWORD` /
`DB_HOST` / `DB_PORT` when both forms are present.

Browser JWT revocation is stored in PostgreSQL table `fastapi_revoked_token`.
Run Alembic before testing login/logout/refresh against a fresh local database.
