.DEFAULT_GOAL := help
-include .env.local

PYTHON ?= uv run python
EVAL_RUNNER := run_eval.py
JUDGE_VALIDATOR := validate_judge.py
CASES ?= cases.json
GROUND_TRUTH ?= judge_ground_truth.json
RESULTS_DIR ?= results
PROMPT_VERSION ?= document_generation_v002
TEMPLATE ?=
JUDGE_PROMPT_VERSION ?= clinical_document_judge_v002
JUDGE_PROVIDER ?= openai
JUDGE_MODEL ?= gpt-5.4
ANTHROPIC_JUDGE_MODEL ?= claude-opus-4-8
JUDGES ?=
GEMINI_MODEL ?= gemini-3.5-flash
ANTHROPIC_MODEL ?= claude-haiku-4-5-20251001
OPENAI_MODEL ?= gpt-5.4-mini
OPENAI_REASONING_EFFORT ?= none
ANTHROPIC_THINKING_BUDGET ?=
MODELS ?= gemini:$(GEMINI_MODEL),anthropic:$(ANTHROPIC_MODEL)
COUNT ?=
LAST ?=
CASE_ID ?=
GENERATION_ARGS := $(if $(OPENAI_REASONING_EFFORT),--openai-reasoning-effort "$(OPENAI_REASONING_EFFORT)",) $(if $(ANTHROPIC_THINKING_BUDGET),--anthropic-thinking-budget "$(ANTHROPIC_THINKING_BUDGET)",)
CASE_ARGS := $(if $(COUNT),--count "$(COUNT)",) $(if $(LAST),--last "$(LAST)",) $(if $(CASE_ID),--case-id "$(CASE_ID)",)
TEMPLATE_ARGS := $(if $(TEMPLATE),--template-file "$(TEMPLATE)",)

.PHONY: help run compare gemini anthropic openai custom validate-judge evals-docgen evals-docgen-gemini evals-docgen-anthropic evals-docgen-openai evals-docgen-compare evals-docgen-custom evals-docgen-validate-judge

help:
	@printf "Available targets:\n"
	@printf "  make compare               Compare Gemini vs Anthropic with defaults from .env.local\n"
	@printf "  make gemini                Run evals only with the Gemini model\n"
	@printf "  make anthropic             Run evals only with the Anthropic model\n"
	@printf "  make openai                Run evals only with the OpenAI model\n"
	@printf "  make custom MODELS=...     Run evals with explicit model overrides\n"
	@printf "  make run                   Run evals with MODELS as currently configured\n"
	@printf "  make validate-judge        Check the judge against ground-truth trap cases\n"
	@printf "\n"
	@printf "Configurable variables:\n"
	@printf "  CASES=%s\n" "$(CASES)"
	@printf "  TEMPLATE=%s\n" "$(TEMPLATE)"
	@printf "  COUNT=%s\n" "$(COUNT)"
	@printf "  LAST=%s\n" "$(LAST)"
	@printf "  CASE_ID=%s\n" "$(CASE_ID)"
	@printf "  PROMPT_VERSION=%s\n" "$(PROMPT_VERSION)"
	@printf "  JUDGE_PROMPT_VERSION=%s\n" "$(JUDGE_PROMPT_VERSION)"
	@printf "  JUDGES=%s\n" "$(JUDGES)"
	@printf "  JUDGE_PROVIDER=%s\n" "$(JUDGE_PROVIDER)"
	@printf "  JUDGE_MODEL=%s\n" "$(JUDGE_MODEL)"
	@printf "  ANTHROPIC_JUDGE_MODEL=%s\n" "$(ANTHROPIC_JUDGE_MODEL)"
	@printf "  GEMINI_MODEL=%s\n" "$(GEMINI_MODEL)"
	@printf "  ANTHROPIC_MODEL=%s\n" "$(ANTHROPIC_MODEL)"
	@printf "  OPENAI_MODEL=%s\n" "$(OPENAI_MODEL)"
	@printf "  OPENAI_REASONING_EFFORT=%s\n" "$(OPENAI_REASONING_EFFORT)"
	@printf "  ANTHROPIC_THINKING_BUDGET=%s\n" "$(ANTHROPIC_THINKING_BUDGET)"
	@printf "  RESULTS_DIR=%s\n" "$(RESULTS_DIR)"
	@printf "\n"
	@printf "Examples:\n"
	@printf "  make compare\n"
	@printf "  make compare COUNT=1\n"
	@printf "  make compare LAST=6\n"
	@printf "  make gemini COUNT=2\n"
	@printf "  make anthropic TEMPLATE=templates/clinical_document_template_v003.md\n"
	@printf "  make openai TEMPLATE=templates/clinical_document_template_v004.md\n"
	@printf "  make openai OPENAI_REASONING_EFFORT=high\n"
	@printf "  make anthropic ANTHROPIC_THINKING_BUDGET=4096\n"
	@printf "  make compare JUDGES=\"openai:$(JUDGE_MODEL),anthropic:$(ANTHROPIC_JUDGE_MODEL)\"\n"
	@printf "  make custom MODELS=gemini:gemini-3-flash-preview,anthropic:claude-haiku-4-5-20251001 CASE_ID=control-hta-dm2-medicacion\n"

run: evals-docgen
compare: evals-docgen-compare
gemini: evals-docgen-gemini
anthropic: evals-docgen-anthropic
openai: evals-docgen-openai
custom: evals-docgen-custom
validate-judge: evals-docgen-validate-judge

evals-docgen:
	cd ../../document_generation_worker && \
	$(PYTHON) ../evals/document_generation/$(EVAL_RUNNER) \
		--cases "../evals/document_generation/$(CASES)" \
		--prompt-version "$(PROMPT_VERSION)" \
		--models "$(MODELS)" \
		$(if $(JUDGES),--judges "$(JUDGES)",) \
		--judge-provider "$(JUDGE_PROVIDER)" \
		--judge-model "$(JUDGE_MODEL)" \
		--judge-prompt-version "$(JUDGE_PROMPT_VERSION)" \
		--results-dir "../evals/document_generation/$(RESULTS_DIR)" \
		$(TEMPLATE_ARGS) \
		$(GENERATION_ARGS) \
		$(CASE_ARGS)

evals-docgen-compare:
	$(MAKE) evals-docgen \
		MODELS="gemini:$(GEMINI_MODEL),anthropic:$(ANTHROPIC_MODEL)"

evals-docgen-gemini:
	$(MAKE) evals-docgen MODELS="gemini:$(GEMINI_MODEL)"

evals-docgen-anthropic:
	$(MAKE) evals-docgen MODELS="anthropic:$(ANTHROPIC_MODEL)"

evals-docgen-openai:
	$(MAKE) evals-docgen MODELS="openai:$(OPENAI_MODEL)"

evals-docgen-custom:
	@if [ -z "$(MODELS)" ]; then echo "Usage: make evals-docgen-custom MODELS=gemini:model,anthropic:model"; exit 1; fi
	$(MAKE) evals-docgen MODELS="$(MODELS)"

evals-docgen-validate-judge:
	cd ../../document_generation_worker && \
	$(PYTHON) ../evals/document_generation/$(JUDGE_VALIDATOR) \
		--ground-truth "../evals/document_generation/$(GROUND_TRUTH)" \
		--judge-provider "$(JUDGE_PROVIDER)" \
		--judge-model "$(JUDGE_MODEL)" \
		--judge-prompt-version "$(JUDGE_PROMPT_VERSION)"
