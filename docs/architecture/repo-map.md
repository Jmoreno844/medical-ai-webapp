# Mapa del Repositorio

Esta es la guía corta para retomar contexto rápido y editar con menos ambigüedad.

## Qué vive dónde

| Carpeta | Rol | Fuente de verdad |
|--------|-----|------------------|
| `backend/` | API central, modelos, auth, JWT, SSE y orquestación | Sí |
| `backend_fastapi/` | Nueva API FastAPI en migración paralela; no reemplaza a Django hasta completar contratos | Sí |
| `cloud_functions/` | Transcripción y generación documental con Gemini | Sí |
| `webapp/` | SPA del médico | Sí |
| `infra/` | Infra GCP, IAM, budgets, deploy base | Sí |
| `landing-page/` | Sitio marketing separado | Sí, pero no es parte del flujo clínico central |
| `docs/` | Contratos operativos y arquitectura | Sí |
| `webapp/dist/`, `webapp/node_modules/`, `landing-page/.next/`, `landing-page/node_modules/`, `backend/.venv/`, `infra/**/.terraform/` | Artefactos locales o build output | No |

## Límites de negocio

- `backend/apps/encounters/`
  - Dueño del ciclo de vida del encuentro y metadatos del audio.
  - También concentra la lógica de GCS signed URLs en `services/storage.py`.
- `backend/apps/documents/`
  - Dueño del CRUD documental, SSE, callbacks desde Cloud Functions y kickoff de generación.
  - Es la zona más sensible para streaming y coordinación backend <-> frontend <-> functions.
- `backend/apps/generative_ai/`
  - Solo inicia transcripción y decide si usar Cloud Tasks o llamada HTTP directa.
  - No es el dueño del stream SSE ni del almacenamiento final del documento.
- `backend/apps/templates/`
  - Dueño de plantillas base y plantillas del médico.
- `backend/apps/patients/`
  - Dueño del modelo de paciente y relación médico-paciente.
- `backend/apps/users/`
  - Dueño de sesión Django y JWT de usuario.
- `backend_fastapi/`
  - Implementación paralela de la migración Django -> FastAPI.
  - Tiene su propio proyecto `uv` (`pyproject.toml` y `uv.lock`) separado del
    entorno Django.
  - Organiza endpoints, schemas y servicios por dominio en `app/domains/*`;
    `app/api/v1/router.py` solo compone routers.
  - Expone rutas nuevas bajo `/api/v1` y conserva SSE en memoria durante la primera fase.
  - No debe introducir nuevas responsabilidades clínicas que aún no estén cubiertas por tests de contrato contra Django.
- `cloud_functions/functions/endpoints/`
  - Adaptadores HTTP; validan request y delegan.
- `cloud_functions/functions/services/`
  - Lógica de negocio serverless y callbacks a Django.
- `webapp/src/contexts/`
  - Fuente de verdad oficial del estado del detalle de encuentro y de sus side effects compartidos.
- `webapp/src/features/`
  - UI y composición de pantallas. No debe convertirse en una segunda capa de ownership para SSE o estado compartido del detalle de encuentro.

## Si quieres cambiar X

- Nuevo endpoint de backend:
  - `backend/config/urls.py`
  - app correspondiente en `backend/apps/*/api.py`
  - `schemas.py`
  - tests
- Transcripción:
  - Django kickoff: `backend/apps/generative_ai/api.py`
  - Cola: `backend/apps/generative_ai/services/transcription_tasks.py`
  - Function: `cloud_functions/functions/endpoints/transcription_endpoint.py`
  - Callback a Django: `cloud_functions/functions/services/django_api.py`
- Generación documental:
  - Django kickoff: `backend/apps/documents/api/generation.py`
  - Background runner: `backend/apps/documents/services/generation_runner.py`
  - SSE y callbacks: `backend/apps/documents/api/sse.py`, `backend/apps/documents/api/callbacks.py`
  - Function: `cloud_functions/functions/endpoints/document_workflow.py`
- Estado del encuentro en frontend:
  - `webapp/src/contexts/AppProviders.tsx`
  - `webapp/src/contexts/*.tsx`
  - UI: `webapp/src/features/encuentroHeader/`, `webapp/src/features/encuentroTextArea/`
- Infra o deploy:
  - `infra/`
  - `.github/workflows/`
  - `docs/architecture/gcp-infrastructure.md`

## Zonas sensibles

### Auth y seguridad

- Navegador -> Django usa sesión + CSRF.
- Cloud Functions -> Django usa Bearer JWT de vida corta.
- SSE usa un token distinto y de vida corta.
- Si cambias claims, expiración o propósito de un token, actualiza Django, Cloud Functions y docs en el mismo cambio.

### Data models y migraciones

- Los modelos viven en `backend/apps/*/models.py`.
- Las migraciones son parte del contrato del sistema; no las regeneres “por si acaso”.
- Si renombras un campo, actualiza también schemas, frontend, docs y cualquier payload de Cloud Functions.

### Background jobs

- En `stg/prod`, la transcripción debe salir por Cloud Tasks cuando la configuración esté presente.
- La generación documental hoy usa un thread en Django para disparar la Cloud Function.
- SSE depende de un hub en memoria; por decisión actual se mantiene sin Redis en la primera migración FastAPI y limita Cloud Run a una instancia.

### Integraciones externas

- GCS:
  - signed URLs se generan en backend
  - el navegador sube audio directo al bucket
- Gemini:
  - solo vive en Cloud Functions
- Secret Manager / IAM / budgets:
  - viven en `infra/`, no en lógica de producto

### Billing

- No hay un dominio de billing de aplicación.
- Lo único relacionado con costos está en `infra/modules/monitoring` y variables de budget del entorno.

## Decisión de frontend

- Para el detalle de encuentro, la ruta oficial es `AppProviders -> contexts -> feature components`.
- `contexts/` orquesta SSE, kickoff de procesos y estado compartido.
- `features/` consume ese estado y renderiza UI.

## Qué revisar antes de un cambio grande

1. `AGENTS.md`
2. [`system-overview.md`](system-overview.md)
3. Docs específicas del área sensible
4. El módulo real que hoy usa producción, no un helper viejo o duplicado
