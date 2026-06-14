# AI Pipeline

Local R&D harness for experimental AI pipeline steps. Not deployed to production.

| Path | Purpose |
|---|---|
| `common/` | Shared providers, case loading, prompts, JSON utils |
| `templates/` | Shared clinical document templates (classification + generation) |
| `cases/` | Shared fixtures: transcripts, cluster classification cases, context docs |
| `clustering/` | Group turns by clinical topic |
| `filtering/` | Drop non-clinical turns (sparse `drop_turn_ids`) |
| `classification/` | Assign pre-clustered turns to template sections |
| `generation/` | Generate document section content from classified clusters |
| `context_pipeline/` | Doctor notes + patient PDFs → claims → section routing |
| `ui/` | Streamlit app for E2E or per-step runs with result inspection |

## Two branches

**Transcript:** `filtering → clustering → classification → generation`

**Context (parallel):** `decompose` + `extract` → `classify_claims` → merge at `generation`

See [`context_pipeline/README.md`](context_pipeline/README.md).

## Setup

```bash
cd ai-pipeline
cp .env.local.example .env.local
# Set API keys / GCP project as needed (see .env.local.example)
uv sync --group dev --group ui
# or: make sync-ui
```

## Run a module

Shared cases live in `cases/`:

- `cases/index.json` + `cases/transcripts/` — full transcript fixtures (filtering, clustering)
- `cases/cluster/` — per-cluster fixtures for classification (`case1/<topic_label>.json`)
- `cases/context/` — doctor notes and PDF fixtures for the context pipeline

From a module directory:

```bash
# Clustering
cd clustering
make debug CASE_ID=case1 PROVIDER=openai

# Filtering (drop non-clinical turns)
cd ../filtering
make debug CASE_ID=case1 PROVIDER=gemini
make batch MODELS=openai:gpt-5.4-mini,anthropic:claude-haiku-4-5-20251001

# Classification (cluster → template sections)
cd ../classification
make debug CASE_ID=case2_dolor_rodilla PROVIDER=openai

# Generation → section content
cd ../generation
make debug-session SESSION_ID=case1 \
  CLASSIFICATION_RESULT=../classification/results/20260612T222321Z_session_case1_groq.json \
  PROVIDER=openai

# Context branch (optional, merges at generation with PROMPT_VERSION=v002)
cd ../context_pipeline/decompose && make debug CASE_ID=case1
cd ../extract && make debug CASE_ID=case1
cd ../classify_claims && make debug-session CASE_ID=case1 \
  DECOMPOSE_RESULT=../decompose/results/<file>.json \
  EXTRACT_RESULT=../extract/results/<file>.json
```

## Streamlit UI

**Use the project venv** — bare `streamlit run` outside `uv` will miss deps like `groq`.

```bash
cd ai-pipeline
make ui
# equivalent:
# uv sync --group dev --group ui
# uv run streamlit run ui/app.py
```

See [`ui/README.md`](ui/README.md) for details.

Default models: OpenAI `gpt-5.4-mini`, Groq `qwen/qwen3-32b`, Gemini
`gemini-2.5-flash` (Vertex AI), Anthropic `claude-haiku-4-5-20251001`.

Cases must stay dummy or de-identified. Do not commit real clinical data.

When a step stabilizes, extract production logic to a worker or `shared/` and keep
this folder as a sandbox. Formal model comparison with judges belongs in `evals/`.
