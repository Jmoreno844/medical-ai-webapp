# Document pipeline offline evals

Compare two `PipelineConfig` variants on shared cases (cost, latency, output).

## Usage

From repo root, with `ai-pipeline` cases or `evals/document_generation/cases.json`:

```bash
cd evals/document_pipeline
uv run python compare_configs.py \
  --cases ../document_generation/cases.json \
  --config-a generation_strategy=single_call_per_section \
  --config-b generation_strategy=draft_refine_two_call
```

Requires API keys in `document_pipeline_worker/.env.local` (or exported env vars).

This harness is manual/offline only — no live A/B traffic.
