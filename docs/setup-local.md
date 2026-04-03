# Guía de Inicio Local

Esta guía busca dejar un entorno local repetible para volver al proyecto rápido después de una pausa.

## Requisitos

- Docker y Docker Compose
- Python 3.10+ y `uv`
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

- `VITE_API_URL=http://localhost:8000`

### Cloud Functions

```bash
cp cloud_functions/functions/.env.example cloud_functions/functions/.env.local
```

Variables clave:

- `ENVIRONMENT=local`
- `GCP_PROJECT`
- `GCP_REGION`
- `GEMINI_MODEL`
- `DJANGO_API_BASE_URL=http://localhost:8000/`

`cloud_functions/docker-compose.yml` ya monta ADC del host en `/app/adc.json`.

### Copilot Agent

```bash
cp copilot_agent/.env.example copilot_agent/.env.local
```

Variables clave:

- `COPILOT_AGENT_DATABASE_URL`
- `COPILOT_LONG_TERM_DATABASE_URL`
- `BACKEND_INTERNAL_BASE_URL=http://localhost:8000`
- `BACKEND_INTERNAL_TIMEOUT_SECONDS=15`
- `COPILOT_SERVICE_SHARED_JWT`
- `COPILOT_ALLOWED_AUDIENCE=app-api-service`
- `COPILOT_BACKEND_AUDIENCE=medical-api`
- `GCP_PROJECT_ID`
- `GCP_REGION`

Para local, el valor recomendado es reutilizar la misma base `medical_web_app` que levanta `make -C backend db-up`. No necesitas crear una DB adicional solo para el agent runtime.

## 2. Base de datos

```bash
make -C backend db-up
```

## 3. Backend Django

```bash
make -C backend sync-dev
make -C backend migrate
make -C backend runserver
```

Opcional:

```bash
make -C backend createsuperuser
```

## 4. Frontend

```bash
npm --prefix webapp install
npm --prefix webapp run dev
```

Frontend: `http://localhost:5173`

## 5. Cloud Functions locales

```bash
docker compose -f cloud_functions/docker-compose.yml up --build
```

Puertos locales:

- `8082` — `transcription-endpoint`
- `8083` — `document-workflow`

## 6. Smoke test recomendado

1. Abrir el frontend en `http://localhost:5173`.
2. Crear o abrir un `Encuentro`.
3. Verificar que Django responda en `http://localhost:8000/api/health/`.
4. Confirmar que el flujo de transcripción apunte a `http://localhost:8082`.
5. Confirmar que la generación documental apunte a `http://localhost:8083`.
6. Confirmar que `copilot_agent` responda en `http://localhost:8090/healthz`.

## 7. Checks rápidos

Backend:
```bash
make -C backend check
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

Para el slice actual del broker, backend y `copilot_agent` deben compartir el mismo valor de `COPILOT_SERVICE_SHARED_JWT`. El runtime también usa `COPILOT_BACKEND_AUDIENCE` para firmar las tools internas read-only hacia Django. En local, el path más simple es apuntar `COPILOT_AGENT_DATABASE_URL` y `COPILOT_LONG_TERM_DATABASE_URL` a `medical_web_app`. La migración futura a OIDC/ID token está documentada en [`docs/debt/copilot-agent-runtime.md`](debt/copilot-agent-runtime.md).

## 8. Trazas distribuidas opcionales

Para un trace local de `webapp -> Django -> Cloud Functions -> Django`:

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
- `8000` — backend Django
- `5432` — PostgreSQL local
- `8082` — Cloud Function de transcripción
- `8083` — Cloud Function de generación
- `8090` — copilot agent service
- `16686` — Jaeger UI
- `4318` — OTLP HTTP para Jaeger
