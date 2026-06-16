# AI Pipeline — R&D Harness

Streamlit UI and local tooling for experimenting with the clinical document pipeline.

**Clinical logic lives in** [`../shared/document_pipeline_core/`](../shared/document_pipeline_core/) — this folder is only the harness shell.

## What stays here

| Path | Role |
|------|------|
| `ui/` | Streamlit app, runners, viewers |
| `harness/` | Local paths, fixture loaders, session wiring over cases |
| `cases/` | Transcript/context fixtures for R&D |
| `e2e_runs/` | Saved E2E manifests |
| `*/results/` | Per-step JSON outputs from harness runs |

## What does **not** live here anymore

Prompts, step implementations, orchestrators, and clinical tests are in `document_pipeline_core`. Import only via `document_pipeline_core.*`.

## Dev

```bash
cd ai-pipeline
uv sync --group dev --group ui
uv run pytest ui/tests harness/tests -q
uv run streamlit run ui/app.py
```

Run Streamlit from `ai-pipeline/` (or any cwd — `ui/app.py` bootstraps the project root on `sys.path`).
