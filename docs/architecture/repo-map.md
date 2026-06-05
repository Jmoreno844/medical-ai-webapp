# Mapa del Repositorio

Esta es la guía corta para retomar contexto rápido y editar con menos ambigüedad.

## Qué vive dónde

| Carpeta                                                                                                                                       | Rol                                                                                 | Fuente de verdad                               |
| --------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | ---------------------------------------------- |
| `backend_fastapi/`                                                                                                                            | API central, modelos SQLAlchemy, auth, JWT, SSE, orquestación y migraciones Alembic | Sí                                             |
| `transcription_worker/`                                                                                                                       | Worker Cloud Run para VAD Silero + Gemini de transcripción por secciones            | Sí                                             |
| `document_generation_worker/`                                                                                                                 | Worker Cloud Run para generación documental con provider LLM configurable           | Sí                                             |
| `cloud_functions/`                                                                                                                            | Transcripción legacy                                                                | Sí                                             |
| `webapp/`                                                                                                                                     | SPA del médico                                                                      | Sí                                             |
| `infra/`                                                                                                                                      | Infra GCP, IAM, budgets, deploy base                                                | Sí                                             |
| `landing-page/`                                                                                                                               | Sitio marketing separado                                                            | Sí, pero no es parte del flujo clínico central |
| `docs/`                                                                                                                                       | Contratos operativos y arquitectura                                                 | Sí                                             |
| `webapp/dist/`, `webapp/node_modules/`, `landing-page/.next/`, `landing-page/node_modules/`, `backend_fastapi/.venv/`, `infra/**/.terraform/` | Artefactos locales o build output                                                   | No                                             |

## Límites de negocio

- `backend_fastapi/app/domains/encounters/`
  - Dueño del ciclo de vida del encuentro y metadatos del audio.
  - También concentra la lógica de GCS signed URLs en `services/storage.py`.
- `backend_fastapi/app/domains/documents/`
  - Dueño del CRUD documental, SSE, callbacks, work-items internos y kickoff de generación.
  - Es la zona más sensible para streaming y coordinación backend <-> frontend <-> workers.
- `backend_fastapi/app/domains/transcription/`
  - Dueño de la transcripción legacy y de la transcripción por secciones:
    sesiones, signed URLs por sección, registro idempotente, dispatch a Cloud
    Tasks, callbacks desde `transcription_worker`, status y finalización.
  - Publica eventos por el hub SSE de documentos, pero no es dueño del hub.
- `transcription_worker/`
  - Servicio Cloud Run privado para trabajo computacional de transcripción:
    descarga audio desde GCS, ejecuta VAD Silero ONNX, llama Gemini y devuelve
    resultados saneados a FastAPI.
  - No escribe directamente en PostgreSQL ni publica SSE; FastAPI conserva la
    autoridad clínica y transaccional.
- `document_generation_worker/`
  - Servicio Cloud Run privado para generación documental:
    recibe Cloud Tasks con IDs, pide el work-item clínico a FastAPI, llama
    al provider LLM configurado y devuelve chunks saneados al callback existente.
  - No escribe directamente en PostgreSQL ni publica SSE.
- `backend_fastapi/app/domains/templates/`
  - Dueño de plantillas base y plantillas del médico.
- `backend_fastapi/app/domains/patients/`
  - Dueño del modelo de paciente y relación médico-paciente.
- `backend_fastapi/`
  - Servicio ASGI con proyecto `uv` propio (`pyproject.toml` y `uv.lock`).
  - Organiza endpoints, schemas y servicios por dominio en `app/domains/*`;
    `app/api/v1/router.py` compone los routers bajo `/api/v1`.
  - `app/domains/auth/` es dueño de login/JWT/CSRF de usuario.
  - Alembic aplica el schema clínico completo en bases nuevas (`alembic/baseline/baseline_clinical_v1.sql` vía `0001`). Ver `docs/architecture/backend-fastapi-migration.md`.
  - SSE en memoria en la primera fase; limita Cloud Run a `max-instances=1`.
- `cloud_functions/functions/endpoints/`
  - Adaptadores HTTP; validan request y delegan.
- `cloud_functions/functions/services/`
  - Lógica de negocio serverless y callbacks al API (`BACKEND_API_BASE_URL` / `services/backend_api.py`).
- `webapp/src/contexts/`
  - Fuente de verdad oficial del estado del detalle de encuentro y de sus side effects compartidos.
- `webapp/src/features/`
  - UI y composición de pantallas. No debe convertirse en una segunda capa de ownership para SSE o estado compartido del detalle de encuentro.

## Si quieres cambiar X

- Nuevo endpoint de backend:
  - router de dominio en `backend_fastapi/app/domains/*/`
  - schema de dominio en `backend_fastapi/app/domains/*/schemas.py`
  - composición en `backend_fastapi/app/api/v1/router.py`
  - tests
- Transcripción:
  - Kickoff: `backend_fastapi/app/domains/transcription/api.py`
  - Sesiones/secciones: `backend_fastapi/app/domains/transcription/api.py`
  - Cola: `backend_fastapi/app/domains/transcription/service.py`
  - Worker: `transcription_worker/app/`
  - Gemini async: `transcription_worker/app/gemini.py`
- Generación documental:
  - Kickoff, SSE, callbacks y work-items: `backend_fastapi/app/domains/documents/`
  - Servicios: `backend_fastapi/app/domains/documents/service.py`
  - Worker: `document_generation_worker/app/`
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

- Navegador -> API usa cookies JWT + CSRF.
- Cloud Functions -> API usan Bearer JWT de callback de vida corta.
- SSE usa un token distinto y de vida corta.
- Si cambias claims, expiración o propósito de un token, actualiza API, Cloud Functions y docs en el mismo cambio.

### Data models y migraciones

- Los modelos viven en `backend_fastapi/app/db/models.py`.
- Las migraciones son parte del contrato del sistema; no las regeneres “por si acaso”.
- Si renombras un campo, actualiza también schemas, frontend, docs y cualquier payload de Cloud Functions.

### Background jobs

- En `stg/prod`, la transcripción debe salir por Cloud Tasks hacia
  `transcription_worker`.
- En local, la transcripción por secciones puede llamar
  `TRANSCRIPTION_WORKER_BASE_URL=http://localhost:8091` como fallback sin
  emulador de Cloud Tasks.
- En local, la generación documental puede llamar
  `DOCUMENT_GENERATION_WORKER_BASE_URL=http://localhost:8092` como fallback sin
  emulador de Cloud Tasks.
- SSE depende de un hub en memoria; por decisión actual se mantiene sin Redis en la primera migración FastAPI y limita Cloud Run a una instancia.

### Integraciones externas

- GCS:
  - signed URLs se generan en backend
  - el navegador sube audio directo al bucket
- Gemini:
  - transcripción vive en FastAPI con Google Gen AI SDK async sobre Vertex AI;
    la version near realtime ordena y consolida secciones por `section_index`
  - generación documental vive en `document_generation_worker`
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
