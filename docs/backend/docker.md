# Docker layout (`backend/`)

Dockerfiles stay at **`backend/`** root so Cloud Build and common tooling keep simple paths.

## Files

| File                 | Role                                                                                                                                                                                                              |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Dockerfile`         | **Runtime** image: `DJANGO_SETTINGS_MODULE=config.settings.production`, Gunicorn on **port 8080**, entrypoint runs `scripts/docker/migrate.sh` then starts Gunicorn. Health: `GET /api/health/` on the same port. |
| `Dockerfile.test`    | **Tests**: dev dependencies, `DJANGO_SETTINGS_MODULE=config.settings.test`, default command `pytest`. Used with Compose profile `test`.                                                                           |
| `docker-compose.yml` | **Local dev**: `web` + `db`; `web` uses **develop** settings and `runserver` on 8001. DB init mounts `scripts/docker/init-db.sh`.                                                                                 |

## Scripts

| Path                        | Use                                                       |
| --------------------------- | --------------------------------------------------------- |
| `scripts/docker/init-db.sh` | Postgres init (Compose `db` service).                     |
| `scripts/docker/migrate.sh` | Production container: `migrate` then `exec` Gunicorn CMD. |
| `scripts/docker/cleanup.sh` | `docker compose down -v` + `up --build` (local reset).    |
| `scripts/dev/clear_db.sh`   | Drop/recreate `public` schema via host `psql` + `.env`.   |
| `scripts/test/tests.sh`     | Run pytest from host (same spirit as `Dockerfile.test`).  |

## Compose profiles

- Default: `docker compose up web db` — API on http://localhost:8001.
- Tests: `docker compose --profile test run --rm test` — runs pytest in the test image against `db`.
