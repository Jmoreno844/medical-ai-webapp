# Proyecto AI Médico - Repository Instructions

## Mission

Optimize for fast, safe edits in a medical fullstack product where AI agents are expected to work daily.

Priorities, in order:

1. Preserve correctness and existing behavior.
2. Keep the codebase easy to navigate.
3. Improve documentation and clarity.
4. Reduce ambiguity, duplication, and mixed responsibilities.
5. Avoid unnecessary abstraction or churn.

## Read Order

1. `docs/architecture/repo-map.md`
2. `docs/architecture/system-overview.md`
3. `docs/setup-local.md`
4. `docs/backend/auth-and-jwt.md` before auth, SSE, callback, or token changes
5. `docs/backend/database.md` before model or migration changes
6. `docs/architecture/gcp-infrastructure.md` and `infra/README.md` before deploy, IAM, secrets, or Terraform changes
7. `docs/agent/RUNTIME.md` before changes to the copilot agent runtime, tools, graph, or writer flow

## Repo Map

- `backend_fastapi/` — FastAPI API, SQLAlchemy models, auth, SSE, orchestration, Alembic migrations
- `transcription_worker/` — Cloud Run worker for section transcription
- `document_generation_worker/` — Cloud Run worker for document generation
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
- `backend_fastapi/.venv/`
- `infra/**/.terraform/`

## Architecture Rules

- Browser -> FastAPI uses JWT cookies + CSRF.
- FastAPI -> private workers uses authenticated Cloud Tasks and short-lived callback JWTs.
- Workers -> FastAPI callbacks use Bearer JWTs validated in FastAPI.
- SSE uses a separate short-lived token and an in-memory hub in `backend_fastapi/app/domains/documents/sse_hub.py`.
- Audio uploads go browser -> GCS directly through signed URLs; FastAPI stores metadata and triggers background work.

## Business Boundaries

- `backend_fastapi/app/domains/encounters/` owns encounter lifecycle and audio metadata.
- `backend_fastapi/app/domains/documents/` owns document CRUD, generation kickoff, callbacks, and SSE.
- `backend_fastapi/app/domains/transcription/` owns transcription dispatch and Cloud Tasks integration.
- `backend_fastapi/app/domains/templates/` owns base templates and doctor templates.
- `backend_fastapi/app/domains/auth/` owns login/JWT for user-facing auth.
- `copilot_agent/` owns the LangGraph runtime for the future clinical copilot and must stay outside the backend monolith.
- In the frontend, `webapp/src/workspace/` is the state layer for encounter-document workspace concerns such as tabs, active document, snapshot, draft, derived state, AI session state, and patch-review preparation.
- `webapp/src/contexts/` remains the orchestration and compat layer around encounter detail flows; it owns SSE lifecycle and API side effects while delegating durable workspace state to the stores.
- `webapp/src/features/` should render and compose UI, not become a second owner of shared encounter state, streaming lifecycle, or AI workspace payload assembly.

## Sensitive Domains

### Auth / Security

- Keep browser JWT auth and service JWT auth separate.
- Keep backend user auth separate from copilot service-to-service auth.
- Keep FastAPI -> copilot broker auth separate from `copilot_agent -> FastAPI` tools auth, even if both are temporarily backed by `COPILOT_SERVICE_SHARED_JWT`.
- The current copilot slice supports `patch proposal + review + safe apply`, but the agent still must not write directly to canonical clinical documents; FastAPI owns apply and any future audit trail.
- Temporary cross-service copilot auth debt lives in `docs/debt/copilot-agent-runtime.md`; do not duplicate that explanation in every file.
- If you change JWT claims, token purpose, token TTL, or callback endpoints, update FastAPI, workers, and docs together.
- Never log full transcripts, generated documents, raw secrets, or tokens.

### Data Models / Migrations

- Update models, schemas, API contracts, docs, and tests together.
- Do not regenerate or rewrite migrations casually.
- Keep identifiers in English even when domain language in UI/docs stays Spanish.

### Background Jobs / Streaming

- Transcription may run through Cloud Tasks depending on environment/config.
- Document generation starts in FastAPI and streams back through callbacks + SSE.
- The future copilot runtime must remain a separate Cloud Run service brokered by FastAPI, not a hidden module inside the backend process.
- If you touch the copilot broker/runtime boundary, update the nearest doc and keep `docs/debt/copilot-agent-runtime.md` aligned with any accepted temporary compromise.
- SSE is not multi-instance safe today; treat that as a known constraint, not an accidental bug.

### Billing

- There is no in-app billing domain today.
- Cost controls live in Terraform budgets/monitoring only.

## Edit Strategy

- Prefer small, explicit functions and thin HTTP handlers.
- Inspect nearby files and existing patterns before making changes.
- Infer local conventions from the codebase and prefer matching them over inventing new ones.
- Make the smallest change that solves the problem well.
- Prefer explicit names over clever names.
- Prefer simple structure over hidden magic.
- Do not refactor broadly unless there is a clear benefit.
- Document non-obvious constraints close to the module or in `docs/`.
- When returning to the repo after time away, prefer adding a short module README over spreading tribal knowledge across code comments.
- If you discover duplicate frontend patterns, preserve the active path first and only consolidate when the write scope is clearly safe.
- Do not introduce a second frontend owner for SSE lifecycle or shared encounter-detail state outside the official contexts.
- Do not collapse `snapshot`, `draft`, `derived`, and `patch preview` back into one opaque editor state.
- When a frontend change affects the future AI workspace, update the nearest doc and keep `WorkspaceIndex`/editor mode conventions aligned with the code.

## Creating New Files

- Create a new file only when the responsibility is distinct, the current file mixes unrelated concerns, local documentation is needed, or reuse/discoverability clearly improves.
- Before creating a new file, check whether a good home already exists and whether similar files already exist nearby.
- Match the naming, folder layout, and import style already used in that module.
- Choose highly explicit names and keep each new file focused on one responsibility.
- Avoid thin wrapper files that add no meaningful clarity.

## Folder And Module Organization

- Prefer one folder per clear responsibility and one file per main idea.
- Separate business logic from UI, transport, and persistence when practical.
- Group related utilities together and keep sensitive logic in obvious, well-named places.
- Avoid dumping unrelated helpers into generic utils files.
- Avoid large god files and deep abstractions without a clear payoff.
- If a reusable utility or service is not clearly justified, keep the logic close to the active flow.

## Documentation Policy

- Keep documentation updated as part of the same change whenever behavior, setup, architecture, contracts, or operator workflow changes.
- Do not leave doc updates as “follow-up work” if the code change would confuse a future human or AI agent without them.
- Update the nearest relevant doc:
  - repo-wide workflow or onboarding -> `README.md`, `docs/README.md`, `docs/setup-local.md`
  - architecture or ownership boundaries -> `docs/architecture/`
  - auth, security, SSE, callbacks, or tokens -> `docs/backend/auth-and-jwt.md`
  - data model or migration-impacting changes -> `docs/backend/database.md`
  - copilot agent runtime, tools, graph, or writer flow -> `docs/agent/RUNTIME.md`
  - service-specific behavior -> local `README.md` or `AGENTS.md` near that code
- Prefer leaving high-signal comments inside the relevant file when the context is local to that code path.
- Create a new local `README.md` only when the explanation spans multiple files or would be awkward to keep inside code comments.
- Prefer concise, high-signal docs. Avoid long essays and avoid duplicating the same explanation in many places.
- If a convention is visible in code but undocumented, add it to the nearest relevant doc instead of leaving it implicit.

## New Code Standards

- Write new code so a future agent can modify it safely without needing hidden context.
- Prefer small functions with clear ownership, explicit names, and obvious inputs/outputs.
- Add comments only where they explain intent, constraints, invariants, security assumptions, or tradeoffs.
- Do not add comments that merely narrate syntax or restate the code line-by-line.
- In the frontend workspace, keep these boundaries explicit:
  - `snapshot` = last known canonical content
  - `draft` = local editable content
  - `derived` = streaming, preview, or other non-canonical transient state
  - `patch` = proposed write path, not direct document mutation
- New AI-facing frontend code should read from a `WorkspaceIndex`-style adapter instead of assembling ad hoc payloads inside components.
- When code depends on an external contract, link that intent in code comments briefly and update the matching doc in the same change.
- When introducing a temporary workaround, limitation, or known edge case, leave a short comment explaining why it exists and what would replace it.
- If you see low-value comments, remove or simplify them rather than adding more noise.

## Conventions Extraction

- Preserve visible conventions around validation, error handling, API handlers, state management, data access, naming, testing, logging, background jobs, and security-sensitive operations.
- When patterns are repeated, prefer documenting the convention in the appropriate repo doc instead of letting it remain tribal knowledge.
- Be especially careful not to introduce a second competing pattern in sensitive or high-traffic areas.

## Definition Of Done

- Ensure the solution matches existing project conventions.
- Update docs when behavior, architecture, contracts, or important conventions change.
- Re-check whether any new file introduced is actually justified.
- Remove obvious dead code or noisy comments introduced by the change.
- Run the relevant verification commands when applicable.
- Summarize the change clearly, including any assumptions or remaining risks.

## Behavior For Repo Reviews

- Prioritize structure, naming, documentation gaps, mixed responsibilities, and risky inconsistencies.
- Prefer the smallest useful set of doc or code changes that improves future maintainability.
- Report what changed and what still requires human judgment, especially in sensitive areas.

## Verification

- Backend: `uv --project backend_fastapi run ruff check . && ENVIRONMENT=test uv --project backend_fastapi run pytest -q`
- Frontend: `npm --prefix webapp run lint && npm --prefix webapp run build`
- Workers: `python -m pytest transcription_worker/tests && python -m pytest document_generation_worker/tests`

## Change Notes

- Use Conventional Commits when a commit is requested.
- Keep docs in sync with real ports, paths, and environment variable names.
