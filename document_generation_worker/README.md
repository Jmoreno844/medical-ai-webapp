# Document Generation Worker

Cloud Run worker for clinical document generation. It receives Cloud Tasks with
metadata IDs only, fetches the clinical work item from FastAPI over an internal
authenticated endpoint, streams model output from a configurable LLM provider, and sends
sanitized chunks back to FastAPI callbacks.

FastAPI remains the source of truth for permissions, database writes, canonical
document state, and SSE.

## Local

```bash
cd document_generation_worker
uv sync
ENVIRONMENT=local \
BACKEND_INTERNAL_BASE_URL=http://localhost:8001 \
ANTHROPIC_API_KEY=your-key \
uv run uvicorn app.main:app --host 0.0.0.0 --port 8092 --reload
```

Provider defaults:

- `DOCUMENT_GENERATION_PROVIDER=anthropic_api`
- `DOCUMENT_GENERATION_ANTHROPIC_MODEL=claude-haiku-4-5-20251001`

Supported providers:

- `anthropic_api` for Claude through Anthropic's direct API
- `anthropic_vertex` for Claude through Vertex AI
- `google_vertex` for Gemini through Vertex AI

Backward-compatible aliases still work (`claude`, `anthropic`, `google`,
`google_genai`, `gemini`), but the canonical names above are the ones to keep
using.

To test Claude through Vertex AI, define for example:

```bash
DOCUMENT_GENERATION_PROVIDER=anthropic_vertex
DOCUMENT_GENERATION_MODEL=claude-3-5-sonnet-v2@20241022
GCP_PROJECT_ID=your-project
VERTEX_AI_LOCATION=us-east5
```

To test Gemini through Vertex AI:

```bash
DOCUMENT_GENERATION_PROVIDER=google_vertex
DOCUMENT_GENERATION_MODEL=gemini-3.1-flash-lite-preview
GCP_PROJECT_ID=your-project
VERTEX_AI_LOCATION=global
```

`DOCUMENT_GENERATION_MODEL` overrides the provider-specific defaults for any
provider. For Google, `DOCUMENT_GENERATION_GOOGLE_MODEL` is the explicit fallback.
`DOCUMENT_GENERATION_GEMINI_MODEL` still works as a legacy alias.

Set `DOCUMENT_GENERATION_WORKER_BASE_URL=http://localhost:8092` in
`backend_fastapi/.env.local` to let local FastAPI dispatch document generation
work to this service when Cloud Tasks is not configured.

## Logging

Logs and traces must contain metadata only. Do not log prompts, transcripts,
generated documents, chunks, tokens, raw LLM responses, or full payloads.

## Evals

There is a local-first eval surface for comparing document generation models in
`../evals/document_generation/`.

Run it from `evals/document_generation/`:

```bash
cd ../evals/document_generation
make evals-docgen-compare
```

This eval flow is manual only and is intentionally separate from the normal
pytest suite.

That Makefile still executes the runner through `document_generation_worker` so
it picks up the worker environment naturally.

Useful overrides:

```bash
make evals-docgen-gemini GEMINI_MODEL=gemini-3-flash-preview
make evals-docgen-custom MODELS=gemini:gemini-3-flash-preview,anthropic:claude-haiku-4-5-20251001
```

Inside the eval surface, the `anthropic` alias targets Anthropic's direct API
for model comparisons, which now matches one of the worker's supported providers.
