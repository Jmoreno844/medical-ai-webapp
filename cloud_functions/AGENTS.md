# Cloud Functions Instructions

## Scope

These instructions apply to `cloud_functions/`.

## Read First

- `docs/cloud-functions/README.md`
- `docs/backend/auth-and-jwt.md`
- `cloud_functions/functions/README.md`

## Structure

- `functions/main.py` — exported HTTP functions
- `functions/endpoints/` — request validation and orchestration entrypoints
- `functions/services/transcription/` — audio extraction and speech handling
- `functions/services/document_generation/` — prompt assembly, streaming, formatting
- `functions/services/backend_api.py` — HTTP callbacks to the main backend (FastAPI `/api/v1`)
- `functions/config.py` — environment loading and Gemini config

## Boundaries

- Endpoints should validate and delegate, not accumulate business logic.
- `services/backend_api.py` is the only place that should know callback URL shape and `BACKEND_API_BASE_URL` / `BACKEND_API_VERSION`.
- Cloud Functions do not own persistence; the backend (FastAPI) remains the system of record.
- Keep Cloud Function docs updated whenever payloads, env vars, callback behavior, local ports, or deployment assumptions change.
- Add comments only for intent, retry/streaming constraints, auth assumptions, or Gemini-specific tradeoffs.
- Prefer code that makes request validation and callback flow obvious to a future agent reading only the endpoint and service names.

## Sensitive Areas

- Keep callback JWT handling compatible with `docs/backend/auth-and-jwt.md` and the FastAPI callback decoders.
- Never log full transcript text, generated clinical documents, auth tokens, or secrets.
- Validate `document_id`, `process_id`, and required payload fields before calling Gemini.
- Preserve `validate_only` behavior in document generation; the backend depends on it before spawning the background kickoff.

## Local Runtime Notes

- Local Docker Compose exposes:
  - `8082` transcription
  - `8083` document generation
- Copy `functions/.env.example` to `functions/.env.local` for local work.

## Verification

- `python -m pytest cloud_functions/functions/tests`
- If you change request/response payloads, verify the matching FastAPI callback routes in `backend_fastapi/app/domains/documents/`.
