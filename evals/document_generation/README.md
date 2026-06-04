# Document Generation Evals

Local-first eval surface for comparing clinical document generation models with
an LLM judge.

## Run

From `evals/document_generation/`:

```bash
make compare
```

Notes:

- Defaults come from `.env.local` in this folder.
- The runner is manual/local only and is not part of normal pytest.
- Set `OPENAI_API_KEY` for the OpenAI judge.
- Anthropic eval runs use `ANTHROPIC_API_KEY` directly, not Vertex AI.
- Cases must stay dummy or de-identified.
- Do not log or copy real clinical prompts, transcripts, or generated documents.

Examples:

```bash
make compare
make compare COUNT=1
make gemini COUNT=2
make custom MODELS=gemini:gemini-3-flash-preview,anthropic:claude-haiku-4-5-20251001
make custom CASE_ID=remision-urgencias-neurologica
```

If your Anthropic API account does not have access to Haiku 4.5 yet, switch
the env value or override to:

```bash
ANTHROPIC_MODEL=claude-3-5-haiku-20241022
```

Each output in the results JSON includes:

- `model`
- `generation_metrics.time_to_first_token_ms`
- `generation_metrics.time_after_first_token_ms`
- `generation_metrics.total_generation_ms`
