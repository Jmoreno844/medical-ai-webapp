# Docker layout (`backend_fastapi/`)

Dockerfiles stay at **`backend_fastapi/`** root so Cloud Build and common tooling keep simple paths.

## Files

| File                 | Role                                                                                                                                                                                                              |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `backend_fastapi/Dockerfile` | **Runtime** image: starts `uvicorn` on port **8080** after `docker-entrypoint.sh` runs `alembic upgrade head`. Health: `GET /api/v1/health`. |

## Scripts

| Path | Use |
| ---- | --- |
| `backend_fastapi/docker-entrypoint.sh` | Runs Alembic before starting the ASGI server. |
| `backend_fastapi/scripts/migration_smoke_staging.sh` | Migration smoke: `alembic upgrade head`. |
| `backend_fastapi/scripts/verify_alembic_schema_parity.sh` | Reference-vs-Alembic schema diff. |

## Compose profiles

- Local DB can be started with any PostgreSQL 15 container bound to `5433`; see `docs/setup-local.md`.
- Build: `docker build -t medical-fastapi:local backend_fastapi`.
- Run: `docker run --rm --env-file backend_fastapi/.env.local -p 8001:8080 medical-fastapi:local`.
