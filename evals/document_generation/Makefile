.DEFAULT_GOAL := help
-include .env.local

PYTHON ?= uv run python
EVAL_RUNNER := run_eval.py
CASES ?= cases.json
RESULTS_DIR ?= results
PROMPT_VERSION ?= document_generation_v001
JUDGE_PROMPT_VERSION ?= clinical_document_judge_v001
JUDGE_PROVIDER ?= openai
JUDGE_MODEL ?= gpt-4.1-mini
GEMINI_MODEL ?= gemini-3-flash-preview
ANTHROPIC_MODEL ?= claude-haiku-4-5-20251001
MODELS ?= gemini:$(GEMINI_MODEL),anthropic:$(ANTHROPIC_MODEL)
COUNT ?=
CASE_ID ?=
CASE_ARGS := $(if $(COUNT),--count "$(COUNT)",) $(if $(CASE_ID),--case-id "$(CASE_ID)",)

.PHONY: help run compare gemini anthropic custom evals-docgen evals-docgen-gemini evals-docgen-anthropic evals-docgen-compare evals-docgen-custom

help:
	@printf "Available targets:\n"
	@printf "  make compare               Compare Gemini vs Anthropic with defaults from .env.local\n"
	@printf "  make gemini                Run evals only with the Gemini model\n"
	@printf "  make anthropic             Run evals only with the Anthropic model\n"
	@printf "  make custom MODELS=...     Run evals with explicit model overrides\n"
	@printf "  make run                   Run evals with MODELS as currently configured\n"
	@printf "\n"
	@printf "Configurable variables:\n"
	@printf "  CASES=%s\n" "$(CASES)"
	@printf "  COUNT=%s\n" "$(COUNT)"
	@printf "  CASE_ID=%s\n" "$(CASE_ID)"
	@printf "  PROMPT_VERSION=%s\n" "$(PROMPT_VERSION)"
	@printf "  JUDGE_PROMPT_VERSION=%s\n" "$(JUDGE_PROMPT_VERSION)"
	@printf "  JUDGE_PROVIDER=%s\n" "$(JUDGE_PROVIDER)"
	@printf "  JUDGE_MODEL=%s\n" "$(JUDGE_MODEL)"
	@printf "  GEMINI_MODEL=%s\n" "$(GEMINI_MODEL)"
	@printf "  ANTHROPIC_MODEL=%s\n" "$(ANTHROPIC_MODEL)"
	@printf "  RESULTS_DIR=%s\n" "$(RESULTS_DIR)"
	@printf "\n"
	@printf "Examples:\n"
	@printf "  make compare\n"
	@printf "  make compare COUNT=1\n"
	@printf "  make gemini COUNT=2\n"
	@printf "  make custom MODELS=gemini:gemini-3-flash-preview,anthropic:claude-haiku-4-5-20251001 CASE_ID=control-hta-dm2-medicacion\n"

run: evals-docgen
compare: evals-docgen-compare
gemini: evals-docgen-gemini
anthropic: evals-docgen-anthropic
custom: evals-docgen-custom

evals-docgen:
	cd ../../document_generation_worker && \
	$(PYTHON) ../evals/document_generation/$(EVAL_RUNNER) \
		--cases "../evals/document_generation/$(CASES)" \
		--prompt-version "$(PROMPT_VERSION)" \
		--models "$(MODELS)" \
		--judge-provider "$(JUDGE_PROVIDER)" \
		--judge-model "$(JUDGE_MODEL)" \
		--judge-prompt-version "$(JUDGE_PROMPT_VERSION)" \
		--results-dir "../evals/document_generation/$(RESULTS_DIR)" \
		$(CASE_ARGS)

evals-docgen-compare:
	$(MAKE) evals-docgen \
		MODELS="gemini:$(GEMINI_MODEL),anthropic:$(ANTHROPIC_MODEL)"

evals-docgen-gemini:
	$(MAKE) evals-docgen MODELS="gemini:$(GEMINI_MODEL)"

evals-docgen-anthropic:
	$(MAKE) evals-docgen MODELS="anthropic:$(ANTHROPIC_MODEL)"

evals-docgen-custom:
	@if [ -z "$(MODELS)" ]; then echo "Usage: make evals-docgen-custom MODELS=gemini:model,anthropic:model"; exit 1; fi
	$(MAKE) evals-docgen MODELS="$(MODELS)"
