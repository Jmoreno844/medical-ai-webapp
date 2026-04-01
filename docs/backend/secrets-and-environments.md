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

- **Local:** ADC (recommended) or `.env` + optional `GCP_STORAGE_SERVICE_ACCOUNT_KEY_PATH`.
- **CI/test:** Inject JSON or path via CI secrets; isolated project or bucket where possible.
- **Production:** Platform-injected secrets or Secret Manager; dedicated service account per environment where practical.

See `apps/encounters/services/storage.py` for how the client is built from settings.

## Local ADC (Application Default Credentials)

Use ADC to authenticate to GCP **without** creating service account keys (recommended; compatible with org policies that disable key creation).

### One-time login

```bash
gcloud auth application-default login
gcloud config set project vext-stg
```

### Verify ADC works

```bash
gcloud auth application-default print-access-token >/dev/null
```

### How the backend uses ADC

- With `DJANGO_SETTINGS_MODULE=config.settings.develop`, if you **do not** set `GCP_STORAGE_SERVICE_ACCOUNT_KEY_PATH`, the storage client can use ADC (your user creds from the command above).
- In Cloud Run, ADC comes from the service account attached to the service (e.g. `backend-runner@...`), so you typically **do not** need `SERVICE_ACCOUNT_JSON`.

### Optional: explicit creds file (only if you must)

If you must use a JSON file locally, set `GOOGLE_APPLICATION_CREDENTIALS=/abs/path/key.json` (or `GCP_STORAGE_SERVICE_ACCOUNT_KEY_PATH` for dev settings). Prefer ADC over long-lived keys.
