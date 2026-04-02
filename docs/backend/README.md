# Backend

El `backend/` es la API central del sistema. Orquesta autenticación, encuentros, documentos, SSE y la comunicación con Cloud Functions.

## Qué leer aquí

- [`database.md`](database.md) — modelo de datos, ERD y notas sobre PostgreSQL / SQLite.
- [`auth-and-jwt.md`](auth-and-jwt.md) — sesión Django, JWT de usuario, JWT de callbacks y SSE.
- [`logging.md`](logging.md) — política de logging de Django por entorno.
- [`tracing.md`](tracing.md) — OpenTelemetry, Jaeger local y Cloud Trace en GCP.
- [`secrets-and-environments.md`](secrets-and-environments.md) — variables de entorno y settings modules.
- [`docker.md`](docker.md) — Dockerfiles, Compose y scripts de soporte.

## Mapa rápido del código

- `backend/apps/` — dominios de negocio (`users`, `encounters`, `documents`, `patients`, `templates`, `generative_ai`).
- `backend/config/settings/` — `base`, `develop`, `stg`, `test`, `production` y utilidades de logging.
- `backend/utils/` — autenticación JWT y helpers compartidos.

## Cómo se relaciona con el resto

- Recibe requests del frontend con sesión Django.
- Emite JWT de vida corta para Cloud Functions.
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
