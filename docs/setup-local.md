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
cp backend_fastapi/.env.stg.example backend_fastapi/.env.local
```

Variables clave:

- `JWT_SECRET_KEY`
- `AUDIT_IP_HMAC_SECRET`
- `AUDIT_IP_ENCRYPTION_KEY`
- `COPILOT_AGENT_BASE_URL=http://localhost:8090`
- `COPILOT_SERVICE_SHARED_JWT`
- `COPILOT_AGENT_AUDIENCE=app-api-service`
- `COPILOT_BACKEND_AUDIENCE=medical-api`
- `COPILOT_AGENT_TIMEOUT_SECONDS=60`
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`

Para local, el backend y el contenedor Docker de PostgreSQL usan `5433` por defecto para evitar choques con una instalación nativa en `5432`.

Las variables `AUDIT_*` son obligatorias para probar el audit trail local. En
los settings locales del backend existen defaults de desarrollo, pero si quieres
simular staging conviene usar secretos explícitos.

- `GCS_BUCKET_NAME`
- `GCP_PROJECT_ID`
- `GCP_STORAGE_IMPERSONATED_SERVICE_ACCOUNT`
- `TRANSCRIPTION_TASK_TARGET_URL=http://localhost:8001/api/v1/internal/transcription/tasks`
- `DOCUMENT_GENERATION_TASK_TARGET_URL=http://localhost:8001/api/v1/internal/document-generation/tasks`

Para transcripcion por secciones, `ENVIRONMENT=local` debe usar `BackgroundTasks`
como fallback por defecto. Puedes probar Cloud Tasks real desde local solo si la
cola GCP esta completamente configurada y el worker HTTP es alcanzable desde
Google; `localhost:8001` no sirve como destino real de entrega para Cloud Tasks.

La ruta recomendada para firmar URLs de GCS en local es ADC + impersonación. Usa `GCP_STORAGE_SERVICE_ACCOUNT_KEY_PATH` solo como excepción.

### Frontend

```bash
cp webapp/.env.example webapp/.env.local
```

Por defecto:

- `VITE_API_URL=http://localhost:8001`
- `VITE_UPLOAD_ORIGINAL_AUDIO_ENABLED=true`

La pagina local `/debug/transcripcion` ahora llama a FastAPI bajo
`/api/v1/transcription/debug/sections`; no necesita un `VITE_TRANSCRIPTION_WORKER_URL`
separado, pero el backend local si necesita `TRANSCRIPTION_WORKER_BASE_URL`
apuntando al worker para hacer el bridge de debug.

La transcripción segmentada ahora prepara dos artefactos por sección en el
navegador:

- `original`: blob original de respaldo
- `clipped`: audio recortado para transcripción

Ambos se suben directo a GCS con signed URLs; FastAPI solo firma, valida en GCS
y registra referencias.

El `clipped` ahora se encodea en el navegador con `WebCodecs AudioEncoder`
cuando el browser soporta Opus; si no, cae al fallback `opus-recorder`
servido desde `webapp/public/opus-recorder/encoderWorker.min.js`.

### Document Generation Worker

No hay `.env.example` propio hoy; normalmente se corre exportando variables en la
misma shell o con `document_generation_worker/.env.local`.

Variables clave:

- `ENVIRONMENT=local`
- `BACKEND_INTERNAL_BASE_URL=http://localhost:8001`
- `DOCUMENT_GENERATION_PROVIDER=anthropic_api` por defecto
- `DOCUMENT_GENERATION_MODEL` para override explicito del modelo
- `DOCUMENT_GENERATION_ANTHROPIC_MODEL=claude-haiku-4-5-20251001` como fallback
  cuando el provider efectivo es Anthropic
- `ANTHROPIC_API_KEY` si `DOCUMENT_GENERATION_PROVIDER=anthropic_api`
- `GCP_PROJECT_ID` si el provider usa Vertex AI
- `VERTEX_AI_LOCATION=global` para Gemini; para Claude via Vertex AI usa una
  region compatible como `us-east5`
- `DOCUMENT_GENERATION_GOOGLE_MODEL` como fallback cuando el provider efectivo
  es Google Vertex
- `DOCUMENT_GENERATION_GEMINI_MODEL` sigue funcionando como alias legado del
  fallback de Google

Providers soportados:

- `anthropic_api`
- `anthropic_vertex`
- `google_vertex`
- OTEL local opcional:
  - `OTEL_TRACES_EXPORTER=otlp`
  - `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4318/v1/traces`
  - `OTEL_SERVICE_NAME=vexthealth-document-generation-worker`
  - `OTEL_FORCE_OTLP=1` si tu shell ya tiene `GOOGLE_CLOUD_PROJECT`

Ejemplo por defecto con Anthropic API:

```bash
cd document_generation_worker
uv sync --group dev
ENVIRONMENT=local \
BACKEND_INTERNAL_BASE_URL=http://localhost:8001 \
DOCUMENT_GENERATION_PROVIDER=anthropic_api \
DOCUMENT_GENERATION_MODEL=claude-haiku-4-5-20251001 \
ANTHROPIC_API_KEY=tu-api-key \
uv run uvicorn app.main:app --host 0.0.0.0 --port 8092 --reload
```

Ejemplo con Claude en Vertex AI:

```bash
cd document_generation_worker
uv sync --group dev
ENVIRONMENT=local \
BACKEND_INTERNAL_BASE_URL=http://localhost:8001 \
GCP_PROJECT_ID=tu-proyecto \
DOCUMENT_GENERATION_PROVIDER=anthropic_vertex \
DOCUMENT_GENERATION_MODEL=claude-3-5-sonnet-v2@20241022 \
VERTEX_AI_LOCATION=us-east5 \
uv run uvicorn app.main:app --host 0.0.0.0 --port 8092 --reload
```

### Transcription Worker

Variables clave:

- `ENVIRONMENT=local`
- `BACKEND_INTERNAL_BASE_URL=http://localhost:8001`
- `GCS_BUCKET_NAME`
- `GCP_PROJECT_ID`
- `TRANSCRIPTION_PROVIDER=google_genai` por defecto, o `openai` para pruebas directas
- `TRANSCRIPTION_MODEL` para override explicito del modelo
- `TRANSCRIPTION_GEMINI_MODEL=gemini-2.5-flash` como fallback legado para Gemini
- `TRANSCRIPTION_OPENAI_MODEL=gpt-4o-mini-transcribe` como fallback para OpenAI
- `OPENAI_API_KEY` solo si `TRANSCRIPTION_PROVIDER=openai`
- OTEL local opcional:
  - `OTEL_TRACES_EXPORTER=otlp`
  - `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4318/v1/traces`
  - `OTEL_SERVICE_NAME=vexthealth-transcription-worker`
  - `OTEL_FORCE_OTLP=1` si tu shell ya tiene `GOOGLE_CLOUD_PROJECT`

Ejemplo con OpenAI para pruebas:

```bash
cd transcription_worker
uv sync --group dev
ENVIRONMENT=local \
BACKEND_INTERNAL_BASE_URL=http://localhost:8001 \
GCS_BUCKET_NAME=tu-bucket-audio \
GCP_PROJECT_ID=tu-proyecto \
TRANSCRIPTION_PROVIDER=openai \
TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe \
OPENAI_API_KEY=tu-api-key \
uv run uvicorn app.main:app --host 0.0.0.0 --port 8091 --reload
```

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

Para local, el valor recomendado es reutilizar la misma base `medical_web_app` que usa `backend_fastapi`. No necesitas crear una DB adicional solo para el agent runtime.

La integración LangSmith del `copilot_agent` y de los workers queda limitada a `local` y registra solo metadata sanitizada del request/run. No envía transcripciones completas, documentos generados ni tokens a LangSmith.

## 2. Base de datos

Desde `backend_fastapi/` puedes usar:

```bash
make db-up
```

Si la base es nueva, prepara contenedor + esquema con:

```bash
make db-ready
```

O, si prefieres desde la raíz:

```bash
make -C backend_fastapi db-up
make -C backend_fastapi db-ready
```

Ese target crea o arranca el contenedor local `medical-web-app-db` en `5433`.

```bash
docker run --name medical-web-app-db \
  -e POSTGRES_DB=medical_web_app \
  -e POSTGRES_USER=juan \
  -e POSTGRES_PASSWORD=12345 \
  -p 5433:5433 \
  -d postgres:15 -c 'port=5433'
```

## 3. API principal (FastAPI) y migraciones

`backend_fastapi/` es el proyecto `uv` del API por defecto. En una base **nueva**,
el esquema clínico se crea con **Alembic solamente** (`0001` aplica
`alembic/baseline/baseline_clinical_v1.sql`, equivalente a las tablas
históricas del producto + columnas/índices relevantes, más
`fastapi_revoked_token`).

En una base **nueva** (vacía) el mínimo es:

```bash
cd backend_fastapi && uv run alembic upgrade head
```

Si además quieres entrar al panel `/admin`, crea o promociona un admin con el
script interno:

```bash
cd backend_fastapi
uv run python scripts/create_admin.py \
  --email admin@example.com \
  --name Ada \
  --last-name Lovelace \
  --password 'testpass123'
```

Opciones útiles:

- `--update-password`: si el usuario ya existe, también reemplaza su password.
- `--superuser`: además deja `is_superuser=true`.

En `stg` y `prod`, no se recomienda usar `--password` por CLI. El flujo estándar
es un Cloud Run Job que lee `ADMIN_BOOTSTRAP_PASSWORD` desde Secret Manager. El
runbook completo vive en [`backend/admin-bootstrap.md`](backend/admin-bootstrap.md).

O desde la raíz:

```bash
bash backend_fastapi/scripts/migration_smoke_staging.sh
```

Verificación de paridad (opcional, requiere una base histórica de referencia y
otra creada solo con Alembic, mismas versiones de PostgreSQL):
`bash backend_fastapi/scripts/verify_alembic_schema_parity.sh`.

### 3.1. FastAPI en el host (recomendado para desarrollo)

```bash
cd backend_fastapi
uv sync --group dev
# Tras `alembic upgrade head` según arriba
ENVIRONMENT=local uv run uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

Health: `http://localhost:8001/api/v1/health`

También puedes usar otro puerto si en `8001` sigue levantado otro proceso.

En `stg` y `prod`, este mismo script debe ejecutarse explícitamente por un
operador autorizado. No hay endpoint público para crear admins.

`backend_fastapi` carga en orden `backend_fastapi/.env` y
`backend_fastapi/.env.local`. El archivo `backend_fastapi/.env` contiene
placeholders locales; usa `backend_fastapi/.env.stg.example` y
`backend_fastapi/.env.prod.example` como referencia para variables de despliegue,
sin guardar secretos reales en el repo.

### 3.2. POC local de STT realtime

FastAPI incluye un WebSocket experimental, solo local, para probar Google
Speech-to-Text v2 sin pasar por GCS:

```text
ws://localhost:8001/api/v1/dev/transcription/realtime/stt?language_code=es-US&sample_rate_hertz=16000
```

Requisitos:

- `gcloud auth application-default login`
- `GCP_PROJECT_ID` en `backend_fastapi/.env.local`
- Speech-to-Text API habilitada en el proyecto
- opcional: `GCP_STT_LOCATION=us`, `GCP_STT_MODEL=chirp_3`

El endpoint espera chunks binarios `LINEAR16` PCM mono a 16 kHz y devuelve
eventos JSON `partial` / `final`. Para una prueba manual rápida, abre
`backend_fastapi/scripts/realtime_stt_poc.html` en el navegador con FastAPI
corriendo en `8001`. La implementación vive separada del flujo clínico en
`backend_fastapi/app/domains/transcription/api_test.py` y
`backend_fastapi/app/domains/transcription/test_realtime_stt.py`. No uses audio
real de pacientes ni PHI en este POC.

### 3.3. FastAPI con Docker

Con Postgres ya definido en `backend_fastapi/.env.local`:

```bash
docker build -t medical-fastapi:local backend_fastapi
docker run --rm --env-file backend_fastapi/.env.local -p 8001:8080 medical-fastapi:local
```

En la primera subida, el `docker-entrypoint` ejecuta `alembic upgrade head`
sobre la base vacía.

## 4. Frontend

```bash
npm --prefix webapp install
npm --prefix webapp run dev
```

Frontend: `http://localhost:5173`

## 5. Workers locales

Levanta `transcription_worker` en `8091` y `document_generation_worker` en
`8092` siguiendo los ejemplos de esta guia.

## 6. Smoke test recomendado

1. Abrir el frontend en `http://localhost:5173`.
2. Crear o abrir un `Encuentro`.
3. Verificar que el API responda en `http://localhost:8001/api/v1/health`.
4. Confirmar que el flujo de transcripción apunte al worker interno de FastAPI.
5. Confirmar que la generación documental apunte al worker en `http://localhost:8092`.
6. Confirmar que `copilot_agent` responda en `http://localhost:8090/healthz`.

## 7. Checks rápidos

Backend:

```bash
uv --project backend_fastapi run ruff check .
uv --project backend_fastapi run pytest -q backend_fastapi/tests
```

Frontend:

```bash
npm --prefix webapp run lint
npm --prefix webapp run build
```

Workers:

```bash
python -m pytest transcription_worker/tests
python -m pytest document_generation_worker/tests
```

Copilot agent:

```bash
docker compose -f copilot_agent/docker-compose.yml up --build
```

Para el slice actual del broker, backend y `copilot_agent` deben compartir el mismo valor de `COPILOT_SERVICE_SHARED_JWT`. El runtime también usa `COPILOT_BACKEND_AUDIENCE` para firmar las tools internas read-only hacia el **backend**. En local, el path más simple es apuntar `COPILOT_AGENT_DATABASE_URL` y `COPILOT_LONG_TERM_DATABASE_URL` a `medical_web_app`. La migración futura a OIDC/ID token está documentada en [`docs/debt/copilot-agent-runtime.md`](debt/copilot-agent-runtime.md).

## 8. Trazas distribuidas opcionales

Para un trace local de `webapp -> FastAPI -> Cloud Tasks/worker -> FastAPI`
(mismo camino lógico de producción):

```bash
docker compose -f docker-compose.tracing.yml up -d
```

Luego configura:

- Backend: `OTEL_TRACES_EXPORTER`, `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, `OTEL_SERVICE_NAME`
- Frontend: `VITE_OTEL_EXPORTER_OTLP_TRACES_URL`, `VITE_OTEL_SERVICE_NAME`
- Workers: `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, `OTEL_SERVICE_NAME`

Detalle completo en [`docs/backend/tracing.md`](backend/tracing.md).

## Puertos locales

- `5173` — frontend Vite
- `8001` — API backend (FastAPI)
- `5433` — PostgreSQL local
- `8091` — transcription worker
- `8092` — document generation worker
- `8090` — copilot agent service
- `16686` — Jaeger UI
- `4318` — OTLP HTTP para Jaeger
