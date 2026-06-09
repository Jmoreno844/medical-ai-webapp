# Clinical Extraction Evals

Local-first eval surface for comparing `ClinicalMentionsV2` extraction models
with a single LLM judge.

## Run

From `evals/clinical_extraction/`:

```bash
make compare
```

`make compare` now defaults to three extractor models:

- `gemini:gemini-2.5-flash`
- `openai:gpt-5.4-mini`
- `anthropic:claude-haiku-4-5-20251001`

For each case, those model runs are dispatched in parallel.

This runner reuses the same backend controller as the debug page, but without
requiring the FastAPI server to be up. It calls
`run_debug_clinical_extraction(...)` in-process and posts to the clinical
extraction worker just like the debug flow, so grounding and post-processing
stay aligned with `/api/v1/clinical-extraction/debug/extract`.

Notes:

- Defaults come from `.env.local` in `backend_fastapi/` and `clinical_extraction_worker/`.
- The clinical extraction worker must be running locally, usually on `http://localhost:8093`.
- Set `OPENAI_API_KEY` for the default judge.
- Set provider credentials for the extractor models you want to compare:
  `GCP_PROJECT_ID` for Gemini, `OPENAI_API_KEY` for OpenAI extraction,
  `ANTHROPIC_API_KEY` for Anthropic extraction.
- The default judge is `openai:gpt-5.4` with `JUDGE_REASONING_EFFORT=medium`.
- Extraction always uses the worker runtime prompt in
  `clinical_extraction_worker/app/prompts.py`.
- `EXTRACTION_PROMPT_VERSION` (`v0` or `v1`, default `v1`) is logged in results
  only. Reference copies live in `prompts/clinical_extraction_v0.txt` and
  `prompts/clinical_extraction_v1.txt`.
- `CLINICAL_EXTRACTION_DEBUG_TIMEOUT_SECONDS` defaults to `600` for worker calls.
- `EXTRACTION_MAX_CONCURRENT` defaults to `1` so `make compare` does not overload
  the local worker with three simultaneous LLM extractions.
- `COUNT` and `LAST` only filter cases. They do not change how many models run.
- Cases must stay dummy or de-identified.

Examples:

```bash
make compare
make compare COUNT=1
make compare LAST=6
make openai CASE_ID=medication_question_and_avoid
make custom MODELS=anthropic:claude-haiku-4-5-20251001,openai:gpt-5.4-mini
```

## What gets judged

Each candidate model produces the same debug payload you see in the local UI:

- `raw_mentions`
- `processed_mentions`
- `evidence`
- `grounding_stats`

The judge scores the final `processed_mentions` against:

1. the original diarized transcript,
2. a small reference mention set for the case,
3. the debug grounding stats.

Current dimensions:

- `faithfulness_score`
- `atomicity_score`
- `coding_score`
- `grounding_score`

The judge also returns structured findings:

- `invented_mentions`
- `missing_mentions`
- `atomicity_issues`
- `coding_issues`

Each finding carries `critical`, `major`, or `minor`.

## Results

Every run writes a timestamped JSON file to `results/` with:

- selected cases
- `extraction_prompt_version` and the matching log file under `prompts/`
- extractor model outputs
- judge result per output
- run summary per model

The file is created at run start and updated after each model/case. If the run
is interrupted or crashes, check `run_status` (`partial` vs `completed`) and the
saved `case_results` collected so far.

The summary prints mean dimension scores plus counts of critical invented,
missing, atomicity, and coding issues.
