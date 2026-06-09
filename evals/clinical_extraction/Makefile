.DEFAULT_GOAL := help
-include .env.local

PYTHON ?= uv run --with openai python
EVAL_RUNNER := run_eval.py
CASES ?= cases.json
RESULTS_DIR ?= results
JUDGE_PROMPT_VERSION ?= clinical_extraction_judge_v001
EXTRACTION_PROMPT_VERSION ?= v1
JUDGE_PROVIDER ?= openai
JUDGE_MODEL ?= gpt-5.4
JUDGE_REASONING_EFFORT ?= medium
GEMINI_MODEL ?= gemini-2.5-flash
OPENAI_MODEL ?= gpt-5.4-mini
ANTHROPIC_MODEL ?= claude-haiku-4-5-20251001
MODELS ?= gemini:$(GEMINI_MODEL),openai:$(OPENAI_MODEL),anthropic:$(ANTHROPIC_MODEL)
COUNT ?=
LAST ?=
CASE_ID ?=
CASE_ARGS := $(if $(COUNT),--count "$(COUNT)",) $(if $(LAST),--last "$(LAST)",) $(if $(CASE_ID),--case-id "$(CASE_ID)",)

.PHONY: help run compare gemini openai anthropic custom evals-clinical-extraction evals-clinical-extraction-compare evals-clinical-extraction-gemini evals-clinical-extraction-openai evals-clinical-extraction-anthropic evals-clinical-extraction-custom

help:
	@printf "Available targets:\n"
	@printf "  make compare               Compare default clinical extraction models\n"
	@printf "  make gemini                Run evals only with Gemini\n"
	@printf "  make openai                Run evals only with OpenAI\n"
	@printf "  make anthropic             Run evals only with Anthropic\n"
	@printf "  make custom MODELS=...     Run evals with explicit model overrides\n"
	@printf "  make run                   Run evals with MODELS as currently configured\n"
	@printf "\n"
	@printf "Configurable variables:\n"
	@printf "  CASES=%s\n" "$(CASES)"
	@printf "  COUNT=%s\n" "$(COUNT)"
	@printf "  LAST=%s\n" "$(LAST)"
	@printf "  CASE_ID=%s\n" "$(CASE_ID)"
	@printf "  MODELS=%s\n" "$(MODELS)"
	@printf "  JUDGE_PROVIDER=%s\n" "$(JUDGE_PROVIDER)"
	@printf "  JUDGE_MODEL=%s\n" "$(JUDGE_MODEL)"
	@printf "  JUDGE_REASONING_EFFORT=%s\n" "$(JUDGE_REASONING_EFFORT)"
	@printf "  JUDGE_PROMPT_VERSION=%s\n" "$(JUDGE_PROMPT_VERSION)"
	@printf "  EXTRACTION_PROMPT_VERSION=%s\n" "$(EXTRACTION_PROMPT_VERSION)"
	@printf "  RESULTS_DIR=%s\n" "$(RESULTS_DIR)"
	@printf "\n"
	@printf "Examples:\n"
	@printf "  make compare\n"
	@printf "  make compare COUNT=1\n"
	@printf "  make compare LAST=6\n"
	@printf "  make openai CASE_ID=medication_question_and_avoid\n"
	@printf "  make custom MODELS=anthropic:$(ANTHROPIC_MODEL),openai:$(OPENAI_MODEL)\n"

run: evals-clinical-extraction
compare: evals-clinical-extraction-compare
gemini: evals-clinical-extraction-gemini
openai: evals-clinical-extraction-openai
anthropic: evals-clinical-extraction-anthropic
custom: evals-clinical-extraction-custom

evals-clinical-extraction:
	cd ../../backend_fastapi && \
	$(PYTHON) ../evals/clinical_extraction/$(EVAL_RUNNER) \
		--cases "../evals/clinical_extraction/$(CASES)" \
		--models "$(MODELS)" \
		--judge-provider "$(JUDGE_PROVIDER)" \
		--judge-model "$(JUDGE_MODEL)" \
		--judge-reasoning-effort "$(JUDGE_REASONING_EFFORT)" \
		--judge-prompt-version "$(JUDGE_PROMPT_VERSION)" \
		--extraction-prompt-version "$(EXTRACTION_PROMPT_VERSION)" \
		--results-dir "../evals/clinical_extraction/$(RESULTS_DIR)" \
		$(CASE_ARGS)

evals-clinical-extraction-compare:
	$(MAKE) evals-clinical-extraction MODELS="gemini:$(GEMINI_MODEL),openai:$(OPENAI_MODEL),anthropic:$(ANTHROPIC_MODEL)"

evals-clinical-extraction-gemini:
	$(MAKE) evals-clinical-extraction MODELS="gemini:$(GEMINI_MODEL)"

evals-clinical-extraction-openai:
	$(MAKE) evals-clinical-extraction MODELS="openai:$(OPENAI_MODEL)"

evals-clinical-extraction-anthropic:
	$(MAKE) evals-clinical-extraction MODELS="anthropic:$(ANTHROPIC_MODEL)"

evals-clinical-extraction-custom:
	@if [ -z "$(MODELS)" ]; then echo "Usage: make evals-clinical-extraction-custom MODELS=provider:model"; exit 1; fi
	$(MAKE) evals-clinical-extraction MODELS="$(MODELS)"
