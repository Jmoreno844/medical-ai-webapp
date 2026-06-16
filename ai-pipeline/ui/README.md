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
- **E2E context (opcional)**: nota libre del médico y/o documentos previos del paciente, por separado
- **E2E provider shortcut**: shared provider/model + **Aplicar a todos los pasos** copies to all four main steps; each step expander still has its own provider, model, and prompt version
- **E2E history**: each completed end-to-end run is saved under `e2e_runs/` and can be reloaded from the **Historial** tab
- **Per step**: run or inspect previous results from `{module}/results/`
- **Generation view**: toggle **Vista del contenido** between rendered markdown (**Markdown aplicado**) and the exact persisted string in a code block (**Markdown fuente**, including `{{e:...}}` markers)
- **Contexto externo** (sidebar → Paso individual): Nota del médico → claims (case del repo o texto pegado), Documentos previos → claims, Enrutar claims → secciones
- **Inputs**: transcript cases (repo or pasted JSON), saved filtering/clustering/classification results, or classification fixtures
- **Config per step**: provider, model, prompt version
- **OpenAI GPT 5.4**: thinking level (`reasoning_effort`: none, minimal, low, medium, high, xhigh)

## Notes

- Results are persisted under each module's `results/` folder (same format as `make debug`)
- Generation surfaces (Generation, Run E2E, Historial) share the same **Vista del contenido** toggle; **Markdown fuente** shows persisted `content` without stripping evidence markers
- Gemini requires `GCP_PROJECT_ID` in `.env.local`
- E2E classification/generation use clusters bridged from the clustering output (no manual fixture export)
