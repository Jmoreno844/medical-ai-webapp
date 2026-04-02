# Proyecto AI Médico - Repository Instructions

## Mission

Optimize for fast, safe edits in a medical fullstack product where AI agents are expected to work daily.

## Read Order

1. `docs/architecture/repo-map.md`
2. `docs/architecture/system-overview.md`
3. `docs/setup-local.md`
4. `docs/backend/auth-and-jwt.md` before auth, SSE, callback, or token changes
5. `docs/backend/database.md` before model or migration changes
6. `docs/architecture/gcp-infrastructure.md` and `infra/README.md` before deploy, IAM, secrets, or Terraform changes

## Repo Map

- `backend/` — Django Ninja API, PostgreSQL models, auth, SSE, orchestration
- `cloud_functions/` — transcribe audio and generate clinical documents with Gemini
- `webapp/` — React + TypeScript SPA for doctors
- `infra/` — Terraform for GCP resources, IAM, budgets, deploy foundations
- `landing-page/` — separate marketing site, not part of the clinical flow
- `docs/` — architecture and operational contracts

## Source Of Truth vs Local Noise

Do not treat these as source of truth unless the task is specifically about generated artifacts or local tooling:

- `webapp/dist/`
- `webapp/node_modules/`
- `landing-page/.next/`
- `landing-page/node_modules/`
- `backend/.venv/`
- `backend/logs/`
- `infra/**/.terraform/`

## Architecture Rules

- Browser -> Django uses session auth + CSRF.
- Django -> Cloud Functions uses short-lived service JWTs.
- Cloud Functions -> Django callbacks use Bearer JWTs validated in Django.
- SSE uses a separate short-lived token and an in-memory hub in `backend/apps/documents/services/sse_hub.py`.
- Audio uploads go browser -> GCS directly through signed URLs; Django stores metadata and triggers background work.

## Business Boundaries

- `backend/apps/encounters/` owns encounter lifecycle and audio metadata.
- `backend/apps/documents/` owns document CRUD, generation kickoff, callbacks, and SSE.
- `backend/apps/generative_ai/` owns transcription dispatch and Cloud Tasks integration.
- `backend/apps/templates/` owns base templates and doctor templates.
- `backend/apps/users/` owns login/session/JWT for user-facing auth.
- `cloud_functions/functions/` owns Gemini-facing logic only; it should not grow direct database responsibilities.
- `webapp/src/contexts/` is the current state source of truth for encounter detail flows.

## Sensitive Domains

### Auth / Security

- Keep Django session auth and service JWT auth separate.
- If you change JWT claims, token purpose, token TTL, or callback endpoints, update Django, Cloud Functions, and docs together.
- Never log full transcripts, generated documents, raw secrets, or tokens.

### Data Models / Migrations

- Update models, schemas, API contracts, docs, and tests together.
- Do not regenerate or rewrite migrations casually.
- Keep identifiers in English even when domain language in UI/docs stays Spanish.

### Background Jobs / Streaming

- Transcription may run through Cloud Tasks depending on environment/config.
- Document generation currently starts in Django and streams back through callbacks + SSE.
- SSE is not multi-instance safe today; treat that as a known constraint, not an accidental bug.

### Billing

- There is no in-app billing domain today.
- Cost controls live in Terraform budgets/monitoring only.

## Edit Strategy

- Prefer small, explicit functions and thin HTTP handlers.
- Document non-obvious constraints close to the module or in `docs/`.
- When returning to the repo after time away, prefer adding a short module README over spreading tribal knowledge across code comments.
- If you discover duplicate frontend patterns, preserve the active path first and only consolidate when the write scope is clearly safe.

## Documentation Policy

- Keep documentation updated as part of the same change whenever behavior, setup, architecture, contracts, or operator workflow changes.
- Do not leave doc updates as “follow-up work” if the code change would confuse a future human or AI agent without them.
- Update the nearest relevant doc:
  - repo-wide workflow or onboarding -> `README.md`, `docs/README.md`, `docs/setup-local.md`
  - architecture or ownership boundaries -> `docs/architecture/`
  - auth, security, SSE, callbacks, or tokens -> `docs/backend/auth-and-jwt.md`
  - data model or migration-impacting changes -> `docs/backend/database.md`
  - service-specific behavior -> local `README.md` or `AGENTS.md` near that code
- Prefer leaving high-signal comments inside the relevant file when the context is local to that code path.
- Create a new local `README.md` only when the explanation spans multiple files or would be awkward to keep inside code comments.
- Prefer concise, high-signal docs. Avoid long essays and avoid duplicating the same explanation in many places.

## New Code Standards

- Write new code so a future agent can modify it safely without needing hidden context.
- Prefer small functions with clear ownership, explicit names, and obvious inputs/outputs.
- Add comments only where they explain intent, constraints, invariants, security assumptions, or tradeoffs.
- Do not add comments that merely narrate syntax or restate the code line-by-line.
- When code depends on an external contract, link that intent in code comments briefly and update the matching doc in the same change.
- When introducing a temporary workaround, limitation, or known edge case, leave a short comment explaining why it exists and what would replace it.

## Verification

- Backend: `make -C backend check`
- Frontend: `npm --prefix webapp run lint && npm --prefix webapp run build`
- Cloud Functions: `python -m pytest cloud_functions/functions/tests`

## Change Notes

- Use Conventional Commits when a commit is requested.
- Keep docs in sync with real ports, paths, and environment variable names.
