# Secrets and environments

Use **different values** for local development, CI/test, and production for JWT signing and GCP credentials. That limits blast radius if a `.env` leaks and avoids tokens minted in dev being valid in prod.

## Settings modules (explicit)

| Context | `ENVIRONMENT` |
|---------|---------------|
| Local CLI | `local` |
| Staging / Cloud Run | `stg` |
| Pytest / CI | `test` |
| Production / Cloud Run image | `prod` |

## Required secrets by environment

### Development (`ENVIRONMENT=local`)

| Variable | Notes |
|----------|--------|
| `JWT_SECRET_KEY` | Use a dev-only value. |
| GCS / workers | Bucket path, worker URLs, optional local SA JSON path. |

### Test (`config.settings.test`)

Use **test-only** `JWT_SECRET_KEY`. Do not point test at production databases or buckets.

### Staging (`ENVIRONMENT=stg`)

| Variable | Required |
|----------|----------|
| `JWT_SECRET_KEY` or Secret Manager `jwt-secret-key` | Yes |
| `DB_NAME` | Yes |
| `DB_USER` | Yes; en `stg` es el usuario IAM derivado de `backend-runner` (formato canonical: sin `.gserviceaccount.com`; el backend normaliza el email completo si se le pasa así) |
| `DB_HOST` / `DB_PORT` | Yes; en `stg` quedan `127.0.0.1:5432` vía Cloud SQL Auth Proxy sidecar |
| `TRANSCRIPTION_TASK_TARGET_URL` | Yes |
| `DOCUMENT_GENERATION_TASK_TARGET_URL` | Yes |
| `CLOUD_TASKS_REGION` | Yes |
| `TRANSCRIPTION_QUEUE_NAME` | Yes |
| `DOCUMENT_GENERATION_QUEUE_NAME` | Yes |
| `CLOUD_TASKS_INVOKER_SERVICE_ACCOUNT` | Yes |
| `DOCUMENT_GENERATION_WORKER_SERVICE_ACCOUNT` | Yes |

En `stg`, la conexión a Cloud SQL usa **IAM DB auth + Cloud SQL Auth Proxy**. Ya no se usan `db-user` ni `db-password` como runtime secrets del backend.

### Production (`ENVIRONMENT=prod`)

| Variable | Required |
|----------|----------|
| `JWT_SECRET_KEY` | Yes |
| `DB_*` | Yes (PostgreSQL) |
| `GCS_BUCKET_NAME` | As needed for storage |
| `SERVICE_ACCOUNT_JSON` | JSON string for GCS client when not using dev file path |
| `GCP_STORAGE_SERVICE_ACCOUNT_KEY_PATH` | Optional; local path if used |
| `TRANSCRIPTION_TASK_TARGET_URL` | Required for transcription worker dispatch |
| `DOCUMENT_GENERATION_TASK_TARGET_URL` | Required for document generation worker |

Inject via Cloud Run / Secret Manager; never commit real values.

## GCP credentials policy (summary)

- **Local:** ADC plus service account impersonation for backend signed URLs (recommended); JSON key only as an exception.
- **CI/test:** Inject JSON or path via CI secrets; isolated project or bucket where possible.
- **Staging:** platform ADC del service account `backend-runner`; Cloud SQL vía IAM DB auth.
- **Production:** Platform-injected secrets or Secret Manager; dedicated service account per environment where practical.

See `apps/encounters/services/storage.py` for how the client is built from settings.

## Local ADC (Application Default Credentials)

Use ADC to authenticate to GCP **without** creating service account keys. For this repo's signed-URL endpoint, the recommended local setup is ADC plus impersonation of a dedicated signer service account.

### One-time login

```bash
gcloud auth application-default login
gcloud config set project vext-stg
```

### Verify ADC works

```bash
gcloud auth application-default print-access-token >/dev/null
```

### Recommended local signer setup

Create or reuse a dedicated service account with the minimum required access to the audio bucket, then allow your user to impersonate it:

```bash
gcloud iam service-accounts add-iam-policy-binding \
  backend-local-gcs-signer@vext-stg.iam.gserviceaccount.com \
  --project=vext-stg \
  --member='user:admin@vexthealth.com' \
  --role='roles/iam.serviceAccountTokenCreator'
```

Set these variables in `backend_fastapi/.env.local`:

```env
GCP_PROJECT_ID=vext-stg
GCS_BUCKET_NAME=vext-stg-audio
GCP_STORAGE_IMPERSONATED_SERVICE_ACCOUNT=backend-local-gcs-signer@vext-stg.iam.gserviceaccount.com
```

### How the backend uses local ADC

- With `ENVIRONMENT=local`, the backend first checks `GCP_STORAGE_SERVICE_ACCOUNT_KEY_PATH`.
- If that path is not set, it tries to impersonate `GCP_STORAGE_IMPERSONATED_SERVICE_ACCOUNT` using your local ADC.
- If neither is configured, it falls back to plain ADC, but local `blob.generate_signed_url(...)` may fail because plain user ADC does not provide a private signing key.
- In Cloud Run, ADC comes from the service account attached to the service (e.g. `backend-runner@...`), so you typically **do not** need `SERVICE_ACCOUNT_JSON`.

### Optional: explicit creds file (only if you must)

If your organization temporarily allows service account keys and you must use one locally, set `GCP_STORAGE_SERVICE_ACCOUNT_KEY_PATH=/abs/path/key.json` (or `GOOGLE_APPLICATION_CREDENTIALS`). Treat this as a short-term exception, not the default workflow.
