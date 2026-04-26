# Cierre final del directorio `backend/` (Django)

Este documento resume la “puerta de salida” cuando el monolito ya no se despliega
ni mantiene contratos. Antes, leer
[backend-fastapi-migration.md](../architecture/backend-fastapi-migration.md) y
[fastapi-admin-ops.md](fastapi-admin-ops.md) (admin/Silk como deuda).

## Criterio de aceptación

- **BD nueva:** `cd backend_fastapi && uv run alembic upgrade head` sin
  `manage.py`.
- **Paridad de schema** (misma major de PostgreSQL): `backend_fastapi/scripts/verify_alembic_schema_parity.sh`
  entre una referencia Django y una base creada solo con Alembic, subset de
  tablas del baseline (incl. `fastapi_revoked_token`).
- **Tests:** `make -C backend check` (si aún aplica mientras dure el
  submódulo); `ruff` + `pytest` en `backend_fastapi/`;
  `python -m pytest cloud_functions/functions/tests` con `BACKEND` apuntando a
  la API bajo prueba; `npm --prefix webapp run build`.
- **Smoke** en staging: login, encuentro, URL de subida, transcripción, SSE de
  generación, copilot / patch (según alcance en esa rama).

## Rollback

- Mientras exista rama/artefacto de Django, despliegue de emergencia
  `workflow_dispatch` o pipeline manual documentada en
  [system-overview.md](../architecture/system-overview.md) (stg+).
- Base ya migrada por **solo Alembic** no se “revierte” con
  `alembic downgrade` del `0001` (no soportado); volver a snapshot/restore
  o recrear.

## Limpieza al eliminar el monolito (checklist de PR)

- Retirar `backend/` o archivarlo en otra rama, eliminar `manage.py` de
  `backend/` o scripts de migración y referencias a Django en `docs/`, `AGENTS.md`, `.cursor/rules/`,
  y workflows CI que aún asuman `make -C backend migrate`.
- Actualizar `webapp` y `cloud_functions` hacia **solo** `/api/v1` (sin rutas
  legacy documentadas) y asegurar `docs/backend/auth-and-jwt.md` refleja solo
  FastAPI.
- Ajustar Terraform/Cloud Build para no construir la imagen Django; mantener
  el bucket y Cloud SQL; revisar `infra/` si había tareas vinculadas a Django.

Cada corte concreto debe acompañar commit(s) y actualización de la sección
“Puerta de verificación” en
`docs/architecture/backend-fastapi-migration.md`.
