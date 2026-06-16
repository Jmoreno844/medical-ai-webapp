# document-pipeline-core

Shared clinical logic for the document pipeline: transcript steps, context pipeline v2, generation, prompt registry, and pure orchestrators.

**Consumers**

- `document_pipeline_worker/` — production Cloud Run adapter (callbacks, SSE, work items)
- `ai-pipeline/` — R&D Streamlit harness (fixtures, viewers, local persistence)

**Not included** (stay in adapters): Streamlit UI, local result persistence, HTTP callbacks, SSE, infra logging.

## Layout

| Path | Responsibility |
|------|----------------|
| `document_pipeline_core/common/` | Domain models, providers, prompt runtime, templates loader |
| `document_pipeline_core/filtering/` | Transcript filtering step |
| `document_pipeline_core/clustering/` | Clustering + repair |
| `document_pipeline_core/classification/` | Section classification |
| `document_pipeline_core/context_pipeline/` | Context v2 sub-steps |
| `document_pipeline_core/generation/` | Direct and two-step generation |
| `document_pipeline_core/orchestrators/` | Pure transcript, context, and document pipelines |
| `templates/` | Clinical template JSON files |

## Dev

```bash
cd shared/document_pipeline_core
uv sync --group dev
uv run pytest -q
uv run ruff check .
```
