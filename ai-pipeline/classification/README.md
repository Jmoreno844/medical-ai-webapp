# Classification

Local debug/batch harness to assign a pre-clustered group of turns to one or
more clinical note sections defined by a JSON template.

Pipeline position: **filtering → clustering → classification**.

## Input contract

Each case references one cluster fixture under `cases/<session_id>/`:

```json
{
  "session_id": "case1",
  "topic_label": "cansancio_escaleras_y_palpidez",
  "turns": [
    { "turn_id": 0, "speaker": "MEDICO", "text": "..." }
  ]
}
```

Layout:

```
cases/
├── index.json
├── case1/
│   ├── cansancio_escaleras_y_palpidez.json
│   └── ...
└── case2/
    ├── dolor_rodilla.json
    └── ...
```

Cases manifest (`cases/index.json`):

```json
{
  "id": "case1_cansancio_escaleras_y_palpidez",
  "cluster_file": "case1/cansancio_escaleras_y_palpidez.json",
  "template_id": "minimal_outpatient_v001"
}
```

## Templates

JSON files in `../templates/` define the allowed section vocabulary for both
classification and generation:

- `id`, `name`, `document_kind`
- `classification.guidelines` — global rules for section assignment
- `generation.guidelines` — global rules for section drafting
- `sections[]` with `section_id`, `heading`, `description`, plus per-step
  `classification.guidelines` and `generation.guidelines`

Initial templates in `../templates/`:

| Template | Sections | Notes |
|---|---|---|
| `minimal_outpatient_v001` | 6 | Default en fixtures `cases/` |
| `outpatient_general_v001` | 17 | Consulta externa general (v004 / producción) |
| `consulta_estructurada_v001` | 9 | Subcampos estructurados (ROS, antecedentes, SV, EF) |

Override path via `TEMPLATES_DIR` in the Makefile (default `../templates`).

Production clinical templates are Markdown in the backend; this module uses JSON
for a closed classifier vocabulary. Future work may import `##` headings from
production templates.

## Run

From this directory:

```bash
# v001: one cluster per request (debug)
make debug CASE_ID=case2_dolor_rodilla PROVIDER=openai PROMPT_VERSION=v001

# v002: full session with token-batched multi-cluster requests
make debug-session SESSION_ID=case1 PROVIDER=openai PROMPT_VERSION=v002
INPUT_TOKEN_BUDGET=4000 make debug-session SESSION_ID=case1 PROMPT_VERSION=v002

make batch MODELS=openai:gpt-5.4-mini,groq:qwen/qwen3-32b
```

### Token batching (v002)

Clusters of a session are packed by **tiktoken** weight, not by fixed count:

- `CLASSIFICATION_INPUT_TOKEN_BUDGET` (default `4000`) — max user payload tokens per request
- `CLASSIFICATION_TOKEN_ENCODING` (default `cl100k_base`) — encoding used for budgeting

The planner uses balanced LPT partitioning so batches are evenly sized (e.g. 4+4+4
instead of 5+2). Batches run **in parallel** by default (`CLASSIFICATION_BATCH_CONCURRENCY=0`
means all batches at once). Set `CLASSIFICATION_BATCH_CONCURRENCY=1` to force sequential
execution, or `2`/`3`/… to cap worker count.

Environment and provider defaults are shared via `../common/providers.py`
(see `../.env.local.example`).

## Output contract

### v001 (single cluster)

```json
{
  "section_ids": ["enfermedad_actual", "motivo_consulta"]
}
```

### v002 (session / multi-cluster)

```json
{
  "assignments": [
    {
      "cluster_id": "case1_cansancio_escaleras_y_palpidez",
      "section_ids": ["motivo_consulta", "enfermedad_actual"]
    }
  ]
}
```

Empty `section_ids` means no section applies. The harness enriches headings from the
template and validates that every `section_id` exists in the template.

## Creating cluster cases

1. Run clustering on a filtered transcript, e.g. `case2_filtered`.
2. Open `clustering/results/*_debug_*.json`.
3. Copy one cluster (`topic_label` + `turns`) into `cases/<session_id>/<topic_label>.json`.
4. Register it in `cases/index.json` with `id` like `case1_<topic_label>`.

## Prompts

- `prompts/classification_v001.txt` — single cluster
- `prompts/classification_v002.txt` — multi-cluster session with internal per-cluster thinking

Pass `PROMPT_VERSION=v001` or `v002` to select a file.

### Groq thinking / reasoning (Qwen3, GPT-OSS)

Defaults for `qwen/qwen3-32b`:

| Env var | Default | Values |
|---|---|---|
| `GROQ_REASONING_EFFORT` | `default` | `none`, `default` |
| `GROQ_REASONING_FORMAT` | `parsed` | `raw`, `parsed`, `hidden` |

With `parsed`, Groq returns thinking in `message.reasoning` (separate from JSON `content`).
The harness captures it via `call_llm_detailed()` and persists it in session results:

- `llm_usage_summary` — always (includes `total_reasoning_tokens` when available)
- `batch_outputs[].thinking` — full text when `OUTPUT_DETAIL=full`
- `batch_outputs[].thinking_chars` — compact mode size hint

```bash
make debug-session SESSION_ID=case1 PROMPT_VERSION=v002 PROVIDER=groq OUTPUT_DETAIL=full
```

## Tests

```bash
cd ..
uv run pytest -q classification/tests
```
