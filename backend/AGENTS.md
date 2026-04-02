# Backend Instructions

## Scope

These instructions apply to `backend/`.

## Read First

- `docs/backend/auth-and-jwt.md`
- `docs/backend/database.md`
- `backend/apps/documents/README.md`

## Service Map

- `apps/users/` — session auth, login, user JWT
- `apps/encounters/` — encounter lifecycle, audio metadata, signed URL support
- `apps/patients/` — patient records and doctor-patient association
- `apps/templates/` — base templates, doctor templates, template usage
- `apps/documents/` — document CRUD, generation kickoff, callbacks, SSE
- `apps/generative_ai/` — transcription kickoff and Cloud Tasks dispatch
- `config/settings/` — environment-specific settings
- `utils/` — service JWT encoding, auth helpers, JWT settings

## Ownership Boundaries

- `apps/documents/` owns document generation orchestration and SSE.
- `apps/generative_ai/` owns starting transcription jobs, not saving streamed generation chunks.
- `apps/encounters/services/storage.py` is the place for GCS auth/signed URL behavior.
- Keep Cloud Function callback validation centralized in `apps/documents/api/callbacks.py` and `utils.auth`.

## Editing Rules

- Keep HTTP handlers thin; move orchestration into services when logic grows.
- Use type hints and keep schemas explicit in `schemas.py`.
- Raise `HttpError` with precise status codes for authorization and validation failures.
- Use `logger = logging.getLogger(__name__)`; never `print()`.
- Prefer `select_related` / `prefetch_related` where ownership checks or list endpoints would otherwise fan out.
- Keep backend docs updated when changing auth, models, env vars, callbacks, setup, or operational behavior.
- If a non-obvious backend module grows in complexity, add or refresh a local `README.md` for that area.
- Comments should explain intent, data ownership, auth constraints, side effects, or rollout caveats, not obvious Python syntax.
- When adding new endpoints or services, make the control flow easy to trace for a future agent: clear names, clear schema names, and minimal hidden coupling.

## Sensitive Areas

### Auth

- User-facing auth is session-based plus `/api/auth/jwt-token`.
- Service-to-service auth is separate and must stay separate.
- Do not mix callback JWT handling with `django_auth`.

### SSE / Generation

- `apps/documents/services/sse_hub.py` is in-memory only.
- `process_id` and `document_id` checks are part of the safety contract for generation callbacks.

### Migrations

- If you change `models.py`, inspect generated migrations before keeping them.
- Avoid “cleanup” migrations that only rename things without updating all downstream API contracts.

## Verification

- `make -C backend check`
- `make -C backend test`
- For auth/JWT changes, also inspect `apps/documents/tests/` and `apps/generative_ai/tests/`
