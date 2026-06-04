# Document Generation Worker

Cloud Run worker for clinical document generation. It receives Cloud Tasks with
metadata IDs only, fetches the clinical work item from FastAPI over an internal
authenticated endpoint, streams model output from Vertex AI, and sends
sanitized chunks back to FastAPI callbacks.

FastAPI remains the source of truth for permissions, database writes, canonical
document state, and SSE.

## Local

```bash
cd document_generation_worker
uv sync
ENVIRONMENT=local \
BACKEND_INTERNAL_BASE_URL=http://localhost:8001 \
GCP_PROJECT_ID=your-project \
uv run uvicorn app.main:app --host 0.0.0.0 --port 8092 --reload
```

Provider defaults:

- `DOCUMENT_GENERATION_PROVIDER=google_genai`
- `DOCUMENT_GENERATION_GEMINI_MODEL=gemini-3-flash-preview`

To test Anthropic Claude through Vertex AI, define for example:

```bash
DOCUMENT_GENERATION_PROVIDER=anthropic_vertex
DOCUMENT_GENERATION_MODEL=claude-3-5-sonnet-v2@20241022
VERTEX_AI_LOCATION=us-east5
```

`DOCUMENT_GENERATION_MODEL` overrides the legacy
`DOCUMENT_GENERATION_GEMINI_MODEL` value for either provider.

Set `DOCUMENT_GENERATION_WORKER_BASE_URL=http://localhost:8092` in
`backend_fastapi/.env.local` to let local FastAPI dispatch document generation
work to this service when Cloud Tasks is not configured.

## Logging

Logs and traces must contain metadata only. Do not log prompts, transcripts,
generated documents, chunks, tokens, raw Gemini responses, or full payloads.

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

Inside the eval surface, the `anthropic` alias now targets Anthropic's direct
API for model comparisons. The production worker still keeps its Vertex-based
Anthropic path unchanged.
