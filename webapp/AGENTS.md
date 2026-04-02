# Frontend Instructions

## Scope

These instructions apply to `webapp/`.

## Read First

- `docs/frontend/system-map.md`
- `webapp/src/contexts/README.md`

## Structure

- `src/router.tsx` — routing
- `src/commons/` — shared UI, auth context, hooks, axios helpers
- `src/contexts/` — active encounter-detail state management
- `src/features/` — page and feature UI
- `src/api/` and `src/services/` — API-facing helpers

## Source Of Truth

- For encounter detail flows, `src/contexts/AppProviders.tsx` plus the providers under `src/contexts/` are the current source of truth.
- There are older feature hooks that overlap with current context behavior:
  - `src/features/encuentroTextArea/hooks/useDocumentGeneration.tsx`
  - `src/features/encuentroHeader/hooks/useTranscription.ts`
- Do not extend those legacy hooks unless you are intentionally consolidating the flow.

## Editing Rules

- Keep API traffic on top of `axiosInstance`.
- Keep SSE lifecycle inside contexts/providers, not scattered across presentational components.
- Avoid duplicating the same document state in component-local state when `DocumentContext`, `ContentContext`, `TranscriptionContext`, or `GenerationContext` already owns it.
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
