# Document Pipeline Worker

Cloud Run worker for the multi-step clinical document pipeline v2:

`filtering → clustering → classification → context (v2) → generation`

Clinical logic lives in `shared/document_pipeline_core/`; this service is the production runtime adapter (work item fetch, LLM calls, callbacks/SSE).

## Local

```bash
cd document_pipeline_worker
cp .env.local.example .env.local
uv run uvicorn app.main:app --host 0.0.0.0 --port 8092
```

Backend local default: `DOCUMENT_PIPELINE_WORKER_BASE_URL=http://localhost:8092`

## Configuration

Per-step settings via `PIPELINE_*` env vars (see `app/pipeline/config.py`). Defaults align with the shared core registry (`filtering v002`, `clustering v002`, `classification v004`, context sub-steps v001–v003, generation `direct`).

- `PIPELINE_GENERATION_ROUTE=direct|two_step|cluster_planner|direct_with_evidence|hybrid` — **fallback** for templates that do not declare hybrid section routes. Templates with hybrid support (today: `consulta_estructurada_v001`) always run with `generation_route=hybrid` and each section follows its `generation.preferred_route` from the template JSON.
- Context sub-step prompt versions: `PIPELINE_CONTEXT_*_PROMPT_VERSION`

## Work item contract

FastAPI returns `context_inputs` (structured) plus legacy `context_content` (mirror). The worker reads `context_inputs` first; see `docs/backend/document-generation-work-item.md`.

## Tests

```bash
uv run pytest tests/
```
