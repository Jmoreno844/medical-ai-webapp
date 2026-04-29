# Transcription Worker

Cloud Run worker for segmented audio transcription. It receives Cloud Tasks,
fetches work items from FastAPI, runs Silero ONNX VAD, calls Gemini only for
speech sections, and returns sanitized results to FastAPI callbacks.

FastAPI remains the source of truth for database writes, document merge logic,
encounter state, and SSE.

## Local

```bash
cd transcription_worker
uv sync
ENVIRONMENT=local \
BACKEND_INTERNAL_BASE_URL=http://localhost:8001 \
GCS_BUCKET_NAME=your-audio-bucket \
GCP_PROJECT_ID=your-project \
uv run uvicorn app.main:app --host 0.0.0.0 --port 8091 --reload
```

Set `TRANSCRIPTION_WORKER_BASE_URL=http://localhost:8091` in
`backend_fastapi/.env.local` to let local FastAPI dispatch background section
work to this service when Cloud Tasks is not configured.

## Logging

Logs must contain metadata only. Do not log transcript text, audio bytes, signed
URLs, tokens, raw prompts, raw Gemini responses, or full payloads.
