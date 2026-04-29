# Document Generation Worker

Cloud Run worker for clinical document generation. It receives Cloud Tasks with
metadata IDs only, fetches the clinical work item from FastAPI over an internal
authenticated endpoint, streams Gemini output, and sends sanitized chunks back
to FastAPI callbacks.

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

Set `DOCUMENT_GENERATION_WORKER_BASE_URL=http://localhost:8092` in
`backend_fastapi/.env.local` to let local FastAPI dispatch document generation
work to this service when Cloud Tasks is not configured.

## Logging

Logs and traces must contain metadata only. Do not log prompts, transcripts,
generated documents, chunks, tokens, raw Gemini responses, or full payloads.
