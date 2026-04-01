# Secrets and environments

Use **different values** for local development, CI/test, and production for Django signing, JWT signing, and GCP credentials. That limits blast radius if a `.env` leaks and avoids tokens minted in dev being valid in prod.

## Settings modules (explicit)

| Context | `DJANGO_SETTINGS_MODULE` |
|---------|---------------------------|
| Local CLI (`manage.py` default) | `config.settings.develop` |
| Pytest / CI | `config.settings.test` |
| Gunicorn / Cloud Run image | `config.settings.production` |

Legacy: `DJANGO_SETTINGS_MODULE=config.settings` still loads **develop** (see `config/settings/__init__.py`) but prefer explicit modules.

## Required secrets by environment

### Development (`config.settings.develop`)

| Variable | Notes |
|----------|--------|
| `DJANGO_SECRET_KEY` | Preferred. Falls back to `SECRET_KEY`, then an insecure default (change for shared machines). |
| `JWT_SECRET_KEY` | Separate from Django secret; use a dev-only value. |
| GCS / Cloud Functions | See `develop.py` — bucket path, URLs, optional local SA JSON path. |

### Test (`config.settings.test`)

Use **test-only** `DJANGO_SECRET_KEY` and `JWT_SECRET_KEY` (pytest sets `DJANGO_SETTINGS_MODULE` via `pytest.ini`). Do not point test at production databases or buckets.

### Production (`config.settings.production`)

| Variable | Required |
|----------|----------|
| `DJANGO_SECRET_KEY` | Yes |
| `JWT_SECRET_KEY` | Yes |
| `DB_*` | Yes (PostgreSQL) |
| `GCS_BUCKET_NAME` | As needed for storage |
| `SERVICE_ACCOUNT_JSON` | JSON string for GCS client when not using dev file path |
| `GCP_STORAGE_SERVICE_ACCOUNT_KEY_PATH` | Optional; local path if used |
| `TRANSCRIPTION_CLOUD_FUNCTION_URL` | As needed |
| `GENERATE_DOCUMENT_CLOUD_FUNCTION_URL` | As needed (alias: `GENERATE_DOCUMENT_CLOUD_FUNCTION_BASE_URL`) |

Inject via Cloud Run / Secret Manager; never commit real values.

## GCP credentials policy (summary)

- **Local:** ADC plus service account impersonation for backend signed URLs (recommended); JSON key only as an exception.
- **CI/test:** Inject JSON or path via CI secrets; isolated project or bucket where possible.
- **Production:** Platform-injected secrets or Secret Manager; dedicated service account per environment where practical.

See `apps/encounters/services/storage.py` for how the client is built from settings.

## Local ADC (Application Default Credentials)

Use ADC to authenticate to GCP **without** creating service account keys. For this repo's Django signed-URL endpoint, the recommended local setup is ADC plus impersonation of a dedicated signer service account.

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

Set these variables in `backend/.env`:

```env
GCP_PROJECT_ID=vext-stg
GCS_BUCKET_NAME=vext-stg-audio
GCP_STORAGE_IMPERSONATED_SERVICE_ACCOUNT=backend-local-gcs-signer@vext-stg.iam.gserviceaccount.com
```

### How the backend uses local ADC

- With `DJANGO_SETTINGS_MODULE=config.settings.develop`, the backend first checks `GCP_STORAGE_SERVICE_ACCOUNT_KEY_PATH`.
- If that path is not set, it tries to impersonate `GCP_STORAGE_IMPERSONATED_SERVICE_ACCOUNT` using your local ADC.
- If neither is configured, it falls back to plain ADC, but local `blob.generate_signed_url(...)` may fail because plain user ADC does not provide a private signing key.
- In Cloud Run, ADC comes from the service account attached to the service (e.g. `backend-runner@...`), so you typically **do not** need `SERVICE_ACCOUNT_JSON`.

### Optional: explicit creds file (only if you must)

If your organization temporarily allows service account keys and you must use one locally, set `GCP_STORAGE_SERVICE_ACCOUNT_KEY_PATH=/abs/path/key.json` (or `GOOGLE_APPLICATION_CREDENTIALS`). Treat this as a short-term exception, not the default workflow.
