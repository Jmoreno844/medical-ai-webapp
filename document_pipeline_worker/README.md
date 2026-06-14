# Document Pipeline Worker

Cloud Run worker for the multi-step clinical document pipeline (filtering → clustering → classification → optional context → generation).

## Local

```bash
cd document_pipeline_worker
cp .env.local.example .env.local
uv run uvicorn app.main:app --host 0.0.0.0 --port 8092
```

Backend local default: `DOCUMENT_PIPELINE_WORKER_BASE_URL=http://localhost:8092`

## Configuration

Per-step settings via `PIPELINE_*` env vars (see `app/pipeline/config.py`). Prompts are versioned `.txt` files under `app/pipeline/*/prompts/`. Generation strategy: `PIPELINE_GENERATION_STRATEGY=single_call_per_section`.

## Tests

```bash
uv run pytest tests/
```
