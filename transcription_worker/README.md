# Transcription Worker

Cloud Run worker for segmented audio transcription. It receives Cloud Tasks,
fetches work items from FastAPI, runs Silero ONNX VAD, calls the configured
transcription model only for speech sections, and returns sanitized results to
FastAPI callbacks.

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

Provider defaults:

- `TRANSCRIPTION_PROVIDER=google_genai`
- `TRANSCRIPTION_GEMINI_MODEL=gemini-2.5-flash`

Testing with OpenAI direct upload from the worker:

```bash
TRANSCRIPTION_PROVIDER=openai
TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe
OPENAI_API_KEY=your-key
```

With `google_genai`, the worker keeps sending `gs://...` references to Vertex
AI. With `openai`, the worker reuses the downloaded audio bytes from VAD and
sends the section file directly to OpenAI only for the transcription request.

Set `TRANSCRIPTION_WORKER_BASE_URL=http://localhost:8091` in
`backend_fastapi/.env.local` to let local FastAPI dispatch background section
work to this service when Cloud Tasks is not configured.

For local debugging only, the worker also exposes:

```text
POST /api/v1/dev/transcription/debug
```

It accepts a multipart audio file plus optional `provider` / `model` override
and is used by the frontend debug page at `/debug/transcripcion`.

## Logging

Logs must contain metadata only. Do not log transcript text, audio bytes, signed
URLs, tokens, raw prompts, raw Gemini responses, or full payloads.
