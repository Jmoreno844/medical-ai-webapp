# Clustering

Local debug/batch harness to group medical conversation turns by clinical topic.

## Input contract

Cases reference transcript JSON aligned with `shared/transcription_contract`:

- `session_id`
- `chunks[]` with `chunk_id` and `turns[]`
- each turn has `turn_id` (int), `speaker` and `text`

`turn_id` is stored in the transcript JSON so the model sees the same ids in
the input payload. Use sequential integers `0, 1, 2, ...` across all chunks in
order. If `turn_id` is omitted, the loader infers it from order.

## Run

From this directory:

```bash
make debug CASE_ID=case1 PROVIDER=openai
make debug CASE_ID=case1 PROVIDER=gemini
make debug CASE_ID=case1 PROVIDER=anthropic
make batch MODELS=openai:gpt-5.4-mini,gemini:gemini-2.5-flash
make batch CASE_ID=eval_doc_clinica_co_001
```

Environment:

- `OPENAI_API_KEY` for OpenAI
- `GROQ_API_KEY` for Groq
- `ANTHROPIC_API_KEY` for Anthropic API
- `GCP_PROJECT_ID` (+ ADC) for Gemini on Vertex AI
- Optional overrides in `.env.local` (see `../.env.local.example`)

Default models:

| Provider | Default model |
|---|---|
| OpenAI | `gpt-5.4-mini` |
| Groq | `qwen/qwen3-32b` |
| Gemini | `gemini-2.5-flash` |
| Anthropic | `claude-haiku-4-5-20251001` |

Provider-specific LLM config (`../common/providers.py`):

| Provider | Output limit env | JSON mode env |
|---|---|---|
| OpenAI | `OPENAI_MAX_COMPLETION_TOKENS` | `OPENAI_JSON_MODE` |
| Groq | `GROQ_MAX_TOKENS` | `GROQ_JSON_MODE` (`auto` retries on failure) |
| Gemini | `GEMINI_MAX_OUTPUT_TOKENS` | `GEMINI_JSON_MODE` |
| Anthropic | `ANTHROPIC_MAX_TOKENS` | prompt-only JSON |

Gemini uses `GEMINI_LOCATION` or `GCP_REGION` (default `global` for all models).
Alias `google:model` is accepted as `gemini:model`. Gemini 3 models disable
models disable internal thinking (`thinking_budget=0`) so JSON output is not
consumed by reasoning tokens on large prompts.

## Cases

Shared fixtures under `../cases/`:

- `index.json` — manifest with `id`, `transcript_file`, optional `notes`
- `transcripts/*.json` — transcript payloads

Do not commit real PHI. Keep fixtures dummy or de-identified.

## Prompts

Versioned flat files in `prompts/`:

- `clustering_v001.txt`

Pass `PROMPT_VERSION=v001` to select a file. Results JSON records `prompt_version`
and `prompt_file`.

## Output

The LLM must return JSON matching:

```json
{
  "clusters": [
    {
      "topic_label": "medicacion",
      "turn_ids": [0, 1]
    }
  ],
  "unassigned_turn_ids": []
}
```

`make debug` prints clusters and turn coverage to stdout, and writes JSON to
`results/{timestamp}_debug_{case_id}_{provider}.json`. Each cluster in the JSON
includes `turns` with `turn_id`, `speaker` and `text` from the case transcript.
Incomplete turn coverage prints a `WARNING` but still saves the result and exits `0`.
A repair pass (`clustering_repair_v001.txt`) runs automatically when `missing_turn_ids`
are detected (up to 2 passes). Repair assigns only to existing `topic_label` values.

`make batch` writes timestamped JSON under `results/` for multiple cases/models.
Use `OUTPUT_DETAIL=full` to persist raw LLM responses; default `compact` omits them.

## Tests

```bash
cd ../..
uv --project ai-pipeline run pytest -q
```
