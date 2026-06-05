# Backend

`backend_fastapi/` es la API central del sistema. Orquesta autenticación, encuentros, documentos, SSE y la comunicación con los workers privados de transcripción y generación.

## Qué leer aquí

- [`database.md`](database.md) — modelo de datos, ERD y notas sobre PostgreSQL / SQLite.
- [`auth-and-jwt.md`](auth-and-jwt.md) — JWT de usuario, JWT de callbacks y SSE.
- [`audit-trail.md`](audit-trail.md) — auditoría clínica persistente, sesiones y política de IP.
- [`logging.md`](logging.md) — política de logging del backend por entorno.
- [`tracing.md`](tracing.md) — OpenTelemetry, Jaeger local y Cloud Trace en GCP.
- [`secrets-and-environments.md`](secrets-and-environments.md) — variables de entorno y settings modules.
- [`docker.md`](docker.md) — Dockerfiles, Compose y scripts de soporte.

## Mapa rápido del código

- `backend_fastapi/app/domains/` — dominios de negocio (`auth`, `encounters`, `documents`, `patients`, `templates`, `transcription`, `copilot`).
- `backend_fastapi/app/core/settings/` — `local`, `stg`, `test`, `prod` y utilidades de configuración.
- `backend_fastapi/app/core/security.py` — JWT, CSRF y helpers compartidos.

## Cómo se relaciona con el resto

- Recibe requests del frontend con cookies JWT + CSRF.
- Emite JWT de vida corta para callbacks de workers.
- Publica eventos SSE para transcripción y generación en tiempo real.

## Local Development GCS Token Impersonation

In order to avoid distributing long-lived JSON keys, we rely on GCP Service Account Impersonation for local development when testing GCS upload/download presigned URLs.

The infrastructure provisions a special service account:
`backend-local-gcs-signer@<PROJECT_ID>.iam.gserviceaccount.com`

**Setup Steps:**

1. Login using your Google user credentials (make sure to select the correct GCP project):
   ```bash
   gcloud auth application-default login
   ```
2. Ask a GCP project admin to grant your `@gmail.com` (or `@yourcompany.com`) user the role `roles/iam.serviceAccountTokenCreator` on the `backend-local-gcs-signer` service account so you can impersonate it.
3. Configure impersonation locally:
   ```bash
   gcloud config set auth/impersonate_service_account backend-local-gcs-signer@<PROJECT_ID>.iam.gserviceaccount.com
   gcloud auth application-default login --impersonate-service-account=backend-local-gcs-signer@<PROJECT_ID>.iam.gserviceaccount.com
   ```

Now your local backend environment will seamlessly sign URLs via the python google-cloud-storage libraries.
