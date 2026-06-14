# Generation

Local debug harness to generate clinical document **sections** from classified clusters and optional enrichment claims.

Pipeline position:

- **Transcript:** `filtering → clustering → classification → generation`
- **Context (parallel):** `decompose` + `extract` → `classify_claims` → **generation**

## Input

1. Classification session result JSON (`classification_session_result.assignments`)
2. Cluster fixtures from `../cases/cluster/` for the same `session_id`
3. *(Optional)* Claim classification result JSON from `../context_pipeline/classify_claims/results/`

Classification maps **cluster → section_ids**. Claim classification maps **claim → section_ids**. Generation inverts both to **section → clusters[] + enrichment_claims[]** and runs **one LLM call per non-empty section in parallel**.

## Quick start

Transcript only (`generation_v001`):

```bash
cd generation
make debug-session \
  SESSION_ID=case1 \
  CLASSIFICATION_RESULT=../classification/results/20260612T222321Z_session_case1_groq.json \
  PROVIDER=openai \
  OUTPUT_DETAIL=full
```

With context branch (`generation_v002` recommended):

```bash
make debug-session \
  SESSION_ID=case1 \
  CLASSIFICATION_RESULT=../classification/results/<file>.json \
  CLAIM_CLASSIFICATION_RESULT=../context_pipeline/classify_claims/results/<file>.json \
  PROMPT_VERSION=v002 \
  PROVIDER=openai
```

## Prompts

| Version | Use |
|---|---|
| `v001` | Transcript clusters only |
| `v002` | Transcript + `enrichment_claims[]` with source attribution rules |

## Parallelism

| Env var | Default | Meaning |
|---|---|---|
| `GENERATION_SECTION_CONCURRENCY` | `0` | `0` = all sections in parallel; `1` = sequential; `N` = cap workers |

Sections are generated when they have transcript clusters **or** classified enrichment claims (e.g. `examen_fisico` from doctor note only).

## Output contract

Per section LLM response:

```json
{
  "section_id": "enfermedad_actual",
  "content": "## Enfermedad actual\n\n..."
}
```

Session export includes `generation_session_result.sections[]` with `cluster_ids` and `claim_ids` per section.

## Tests

```bash
cd ..
uv run pytest -q generation/tests
```
