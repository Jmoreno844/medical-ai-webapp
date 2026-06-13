# Filtering

Local debug/batch harness to identify transcript turns that should be dropped
before clinical documentation. Unlisted turns are implicitly **KEEP**.

Principle: **ante la duda, conservar**. The LLM returns only `drop_turn_ids`.

## Input contract

Shared cases under `../cases/` (same transcript format as clustering):

- `session_id`
- `chunks[]` with `turn_id`, `speaker`, `text`

## Run

From this directory:

```bash
make debug CASE_ID=case1 PROVIDER=openai
make debug CASE_ID=case1 PROVIDER=gemini
make batch MODELS=openai:gpt-5.4-mini,anthropic:claude-haiku-4-5-20251001
```

Environment and provider defaults are shared via `../common/providers.py`
(see `../.env.local.example`).

## Output contract (sparse)

LLM response:

```json
{
  "drop_turn_ids": [3, 17, 42]
}
```

If every turn should be kept: `{"drop_turn_ids": []}`.

The harness expands this to a full decision map in `results/`:

```json
{
  "drop_turn_ids": [3, 17],
  "keep_turn_ids": [0, 1, 2],
  "decisions": [{"turn_id": 0, "keep": 1, "speaker": "...", "text": "..."}],
  "drop_count": 2,
  "keep_count": 123
}
```

`make debug` prints dropped turns and a summary (`kept=N dropped=M`).
Invalid `drop_turn_ids` (unknown or duplicate) raise an error.

## Prompts

- `prompts/filtering_v001.txt` (Spanish)

Pass `PROMPT_VERSION=v001` to select a file.

## Tests

```bash
cd ..
uv run pytest -q
```
