# AI Pipeline UI

Streamlit app to run the R&D pipeline end-to-end or step by step.

## Setup

```bash
cd ai-pipeline
cp .env.local.example .env.local
# Set API keys (OPENAI_API_KEY, GROQ_API_KEY, etc.)
uv sync --group ui
```

## Run

```bash
cd ai-pipeline
uv run streamlit run ui/app.py
```

## Features

- **End-to-end**: filtering → clustering → classification → generation on a transcript case
- **Per step**: run or inspect previous results from `{module}/results/`
- **Inputs**: transcript cases, saved filtering/clustering/classification results, or classification fixtures
- **Config per step**: provider, model, prompt version
- **OpenAI GPT 5.4**: thinking level (`reasoning_effort`: none, minimal, low, medium, high, xhigh)

## Notes

- Results are persisted under each module's `results/` folder (same format as `make debug`)
- Gemini requires `GCP_PROJECT_ID` in `.env.local`
- E2E classification/generation use clusters bridged from the clustering output (no manual fixture export)
