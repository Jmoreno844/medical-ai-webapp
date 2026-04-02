# Frontend Instructions

## Scope

These instructions apply to `webapp/`.

## Read First

- `docs/frontend/system-map.md`
- `webapp/src/contexts/README.md`

## Structure

- `src/router.tsx` — routing
- `src/commons/` — shared UI, auth context, hooks, axios helpers
- `src/workspace/` — workspace state layer (`WorkspaceStore`, snapshots, drafts, derived state, AI session, patch prep)
- `src/contexts/` — encounter-detail orchestration and compatibility layer
- `src/features/` — page and feature UI
- `src/api/` and `src/services/` — API-facing helpers

## Source Of Truth

- For encounter detail flows, `src/contexts/AppProviders.tsx` still defines provider order and long-lived side effects.
- `src/workspace/` is the state source of truth for tabs, active document, snapshot, draft, derived state, AI session state, and patch-prep state.
- `src/contexts/` should delegate workspace state to the stores and keep ownership of SSE kickoff/orchestration only.
- `src/features/` should render and compose UI, not own duplicate SSE lifecycle or a second source of truth for encounter-detail flows.
- If reusable logic needs extraction, prefer a helper or stateless hook consumed by the owning context instead of a new feature-level state manager.

## Editing Rules

- Keep API traffic on top of `axiosInstance`.
- Keep SSE lifecycle inside contexts/providers, not scattered across presentational components.
- Avoid duplicating the same document state in component-local state when the workspace stores or owning contexts already carry it.
- Keep `snapshot`, `draft`, `derived`, and `patch preview` as separate concepts. Do not hide them behind a single generic `content` state.
- Prefer `WorkspaceIndex` builders/selectors for AI-readable workspace payloads instead of composing ad hoc document lists in UI components.
- Prefer explicit types over `any`.
- Keep frontend docs updated when changing routes, state ownership, setup, env vars, SSE flow, or user-visible interaction contracts.
- Comments should explain state ownership, sequencing, race-condition prevention, or UX constraints, not restate JSX or TypeScript syntax.
- When adding new stateful flows, make ownership explicit so a future agent can tell whether the source of truth lives in a context, hook, or component.

## Sensitive Areas

- Do not store sensitive patient data in `localStorage`.
- Avoid logging tokens, raw medical text, or full API responses.
- If you change the generation or transcription flow, verify both the SSE token request and the `EventSource` path.

## Verification

- `npm --prefix webapp run lint`
- `npm --prefix webapp run build`
