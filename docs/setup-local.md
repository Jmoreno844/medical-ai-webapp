# Guía de Inicio Local

Esta guía busca dejar un entorno local repetible para volver al proyecto rápido después de una pausa.

## Requisitos

- Docker y Docker Compose
- Python 3.14+ y `uv`
- Node.js 20+ y `npm`
- `gcloud auth application-default login`
- Acceso a un proyecto GCP con Vertex AI y bucket de audio

## 1. Variables de entorno

### Backend

```bash
cp backend/.env.example backend/.env
```

Variables clave:

- `DJANGO_SECRET_KEY`
- `JWT_SECRET_KEY`
- `COPILOT_AGENT_BASE_URL=http://localhost:8090`
- `COPILOT_SERVICE_SHARED_JWT`
- `COPILOT_AGENT_AUDIENCE=app-api-service`
- `COPILOT_BACKEND_AUDIENCE=medical-api`
- `COPILOT_AGENT_TIMEOUT_SECONDS=60`
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`

Para local, el backend y el contenedor Docker de PostgreSQL usan `5433` por defecto para evitar choques con una instalación nativa en `5432`.

- `GCS_BUCKET_NAME`
- `GCP_PROJECT_ID`
- `GCP_STORAGE_IMPERSONATED_SERVICE_ACCOUNT`
- `TRANSCRIPTION_CLOUD_FUNCTION_URL=http://localhost:8082`
- `GENERATE_DOCUMENT_CLOUD_FUNCTION_URL=http://localhost:8083`

La ruta recomendada para firmar URLs de GCS en local es ADC + impersonación. Usa `GCP_STORAGE_SERVICE_ACCOUNT_KEY_PATH` solo como excepción.

### Frontend

```bash
cp webapp/.env.example webapp/.env.local
```

Por defecto:

- `VITE_API_URL=http://localhost:8001`

### Cloud Functions

```bash
cp cloud_functions/functions/.env.example cloud_functions/functions/.env.local
```

Variables clave:

- `ENVIRONMENT=local`
- `GCP_PROJECT`
- `GCP_REGION`
- `GEMINI_MODEL`
- `BACKEND_API_BASE_URL=http://localhost:8001`
- `BACKEND_API_VERSION=v1`
- `LANGSMITH_TRACING=true` si quieres tracing local en LangSmith
- `LANGSMITH_API_KEY`
- `LANGSMITH_PROJECT=cloud-functions-local`

`cloud_functions/docker-compose.yml` ya monta ADC del host en `/app/adc.json`.

### Copilot Agent

```bash
cp copilot_agent/.env.example copilot_agent/.env.local
```

Variables clave:

- `COPILOT_LLM_PROVIDER_FAMILY=openai`
- `COPILOT_PLANNER_MODEL=gpt-5.4-mini`
- `COPILOT_PATCH_MODEL=gpt-5.4-mini`
- `OPENAI_API_KEY`
- `LANGSMITH_TRACING=true` para tracing local del runtime
- `LANGSMITH_API_KEY`
- `LANGSMITH_PROJECT=copilot-agent-local`
- `COPILOT_AGENT_DATABASE_URL`
- `COPILOT_LONG_TERM_DATABASE_URL`
- `BACKEND_INTERNAL_BASE_URL=http://localhost:8001` si corres el agente en el host, o `http://host.docker.internal:8001` si corres `copilot_agent` con Docker. En modo Docker, el backend (FastAPI por defecto) debe escuchar en `0.0.0.0:8001`, no solo en `127.0.0.1:8001`.
- `BACKEND_INTERNAL_TIMEOUT_SECONDS=15`
- `COPILOT_SERVICE_SHARED_JWT`
- `COPILOT_ALLOWED_AUDIENCE=app-api-service`
- `COPILOT_BACKEND_AUDIENCE=medical-api`

Si quieres usar Gemini en lugar de OpenAI, cambia `COPILOT_LLM_PROVIDER_FAMILY=google` y define también:

- `GCP_PROJECT_ID`
- `GCP_REGION`
- `VERTEX_MODEL`

Si quieres separar planner y drafter por proveedor/modelo, puedes usar overrides opcionales:

- `COPILOT_PLANNER_PROVIDER_FAMILY`
- `COPILOT_PATCH_PROVIDER_FAMILY`
- `COPILOT_PLANNER_MODEL`
- `COPILOT_PATCH_MODEL`
- `COPILOT_GOOGLE_LOCATION` o los overrides `COPILOT_PLANNER_GOOGLE_LOCATION` / `COPILOT_PATCH_GOOGLE_LOCATION` para modelos Gemini preview.

Para local, el valor recomendado es reutilizar la misma base `medical_web_app` que levanta `make -C backend db-up`. No necesitas crear una DB adicional solo para el agent runtime.

La integración LangSmith del `copilot_agent` y de `cloud_functions` queda limitada a `local` y registra solo metadata sanitizada del request/run. No envía transcripciones completas, documentos generados ni tokens a LangSmith.

## 2. Base de datos

```bash
make -C backend db-up
```

## 3. API principal (FastAPI) y migraciones

`backend_fastapi/` es el proyecto `uv` del API por defecto. En una base **nueva**,
el esquema clínico se crea con **Alembic solamente** (`0001` aplica
`alembic/baseline/baseline_clinical_v1.sql`, equivalente a las tablas
históricas creadas por `manage.py migrate` + columnas/índices relevantes, más
`fastapi_revoked_token`).

En una base **nueva** (vacía) el mínimo es:

```bash
cd backend_fastapi && uv run alembic upgrade head
```

O desde la raíz:

```bash
bash backend_fastapi/scripts/migration_smoke_staging.sh
```

Para comparar o recuperar un flujo con **Django** (solo rollback / auditoría),
`USE_DJANGO_MIGRATE=1 bash backend_fastapi/scripts/migration_smoke_staging.sh` ejecuta antes
`manage.py migrate` y luego Alembic (típicamente inútil en una base ya poblada
por Alembic; ver `docs/architecture/backend-fastapi-migration.md`).

Verificación de paridad (opcional, requiere dos bases: una migrada con Django
y otra con Alembic, mismas versiones de PostgreSQL): `bash backend_fastapi/scripts/verify_alembic_schema_parity.sh` (ver comentario en el script sobre
`ALEMBIC_REF_DJANGO_DB` e incluir `fastapi_revoked_token` en la de referencia si
solo corrió `migrate` sin Alembic previo).

### 3.1. FastAPI en el host (recomendado para desarrollo)

```bash
cd backend_fastapi
uv sync --group dev
# Tras `alembic upgrade head` según arriba
ENVIRONMENT=local uv run uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

Health: `http://localhost:8001/api/v1/health`

También puedes usar el puerto `8002` si en `8001` sigue levantado otro proceso:

`make -C backend fastapi-run` (apunta a `8002`).

`backend_fastapi` carga en orden `backend/.env`, `backend_fastapi/.env` y
`backend_fastapi/.env.local`. El archivo `backend_fastapi/.env` contiene
placeholders locales; usa `backend_fastapi/.env.stg.example` y
`backend_fastapi/.env.prod.example` como referencia para variables de despliegue,
sin guardar secretos reales en el repo.

### 3.2. POC local de STT realtime

FastAPI incluye un WebSocket experimental, solo local, para probar Google
Speech-to-Text v2 sin pasar por GCS:

```text
ws://localhost:8001/api/v1/dev/transcription/realtime/stt?language_code=es-CO&sample_rate_hertz=16000
```

Requisitos:

- `gcloud auth application-default login`
- `GCP_PROJECT_ID` en `backend/.env` o `backend_fastapi/.env.local`
- Speech-to-Text API habilitada en el proyecto
- opcional: `GCP_STT_LOCATION=global`, `GCP_STT_MODEL=chirp_3`

El endpoint espera chunks binarios `LINEAR16` PCM mono a 16 kHz y devuelve
eventos JSON `partial` / `final`. Para una prueba manual rápida, abre
`backend_fastapi/scripts/realtime_stt_poc.html` en el navegador con FastAPI
corriendo en `8001`. La implementación vive separada del flujo clínico en
`backend_fastapi/app/domains/transcription/api_test.py` y
`backend_fastapi/app/domains/transcription/test_realtime_stt.py`. No uses audio
real de pacientes ni PHI en este POC.

### 3.3. FastAPI con Docker (perfil `fastapi`)

Con Postgres ya definido en `backend/.env`:

```bash
make -C backend fastapi-compose-up
# o: (cd backend && docker compose --profile fastapi up -d --build web_fastapi db)
```

No arranques a la vez `web` (Django) y `web_fastapi` mapeando el **mismo**
`BACKEND_PORT` (p. ej. 8001). En la primera subida, el `docker-entrypoint` ejecuta `alembic upgrade head` sobre
la base vacía: no hace falta `manage.py migrate` en esa ruta. El contenedor
`web` (Django) y `web_fastapi` comparten el mismo `POSTGRES_DB` solo si quieres
migrar/auditar con Django; no mezcles ambos en el mismo puerto de API
(Django vs FastAPI).

## 4. Backend Django (solo rollback / referencia)

Mientras exista el monolito, puedes levantar Django con:

```bash
make -C backend sync-dev
make -C backend migrate
make -C backend runserver
```

Django: `http://localhost:8001` — **no** lo uses al mismo tiempo que FastAPI
en el mismo host/puerto.

Opcional:

```bash
make -C backend createsuperuser
```

## 5. Frontend

```bash
npm --prefix webapp install
npm --prefix webapp run dev
```

Frontend: `http://localhost:5173`

## 6. Cloud Functions locales

```bash
docker compose -f cloud_functions/docker-compose.yml up --build
```

Puertos locales:

- `8082` — `transcription-endpoint`
- `8083` — `document-workflow`

## 7. Smoke test recomendado

1. Abrir el frontend en `http://localhost:5173`.
2. Crear o abrir un `Encuentro`.
3. Verificar que el API (FastAPI) responda en `http://localhost:8001/api/v1/health` (Django seguía en `/api/health/` solo si usas el stack legacy).
4. Confirmar que el flujo de transcripción apunte a `http://localhost:8082`.
5. Confirmar que la generación documental apunte a `http://localhost:8083`.
6. Confirmar que `copilot_agent` responda en `http://localhost:8090/healthz`.

## 8. Checks rápidos

Backend:

```bash
make -C backend check
```

Backend FastAPI:

```bash
uv --project backend_fastapi run pytest -q backend_fastapi/tests
```

Frontend:

```bash
npm --prefix webapp run lint
npm --prefix webapp run build
```

Cloud Functions:

```bash
python -m pytest cloud_functions/functions/tests
```

Copilot agent:

```bash
docker compose -f copilot_agent/docker-compose.yml up --build
```

Para el slice actual del broker, backend y `copilot_agent` deben compartir el mismo valor de `COPILOT_SERVICE_SHARED_JWT`. El runtime también usa `COPILOT_BACKEND_AUDIENCE` para firmar las tools internas read-only hacia el **backend** (FastAPI por defecto; Django solo en rollback). En local, el path más simple es apuntar `COPILOT_AGENT_DATABASE_URL` y `COPILOT_LONG_TERM_DATABASE_URL` a `medical_web_app`. La migración futura a OIDC/ID token está documentada en [`docs/debt/copilot-agent-runtime.md`](debt/copilot-agent-runtime.md).

## 9. Trazas distribuidas opcionales

Para un trace local de `webapp -> FastAPI -> Cloud Functions -> FastAPI` (mismo
camino lógico si aún usas el stack legacy con Django en rollback):

```bash
docker compose -f docker-compose.tracing.yml up -d
```

Luego configura:

- Backend: `OTEL_TRACES_EXPORTER`, `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, `OTEL_SERVICE_NAME`
- Frontend: `VITE_OTEL_EXPORTER_OTLP_TRACES_URL`, `VITE_OTEL_SERVICE_NAME`
- Cloud Functions: `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, `OTEL_SERVICE_NAME`

Detalle completo en [`docs/backend/tracing.md`](backend/tracing.md).

## Puertos locales

- `5173` — frontend Vite
- `8001` — API backend (FastAPI por defecto; Django solo en rollback local)
- `5433` — PostgreSQL local
- `8082` — Cloud Function de transcripción
- `8083` — Cloud Function de generación
- `8090` — copilot agent service
- `16686` — Jaeger UI
- `4318` — OTLP HTTP para Jaeger
