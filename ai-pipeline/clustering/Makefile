.DEFAULT_GOAL := help
-include .env.local

PYTHON ?= uv --project .. run python
CASES ?= ../cases/index.json
RESULTS_DIR ?= results
PROMPT_VERSION ?= v001
OUTPUT_DETAIL ?= compact
OPENAI_MODEL ?= gpt-5.4-mini
GROQ_MODEL ?= qwen/qwen3-32b
GEMINI_MODEL ?= gemini-2.5-flash
ANTHROPIC_MODEL ?= claude-haiku-4-5-20251001
PROVIDER ?= openai
MODEL ?=
MODELS ?= openai:$(OPENAI_MODEL),groq:$(GROQ_MODEL)
COUNT ?=
LAST ?=
CASE_ID ?=
CASE_ARGS := $(if $(COUNT),--count "$(COUNT)",) $(if $(LAST),--last "$(LAST)",) $(if $(CASE_ID),--case-id "$(CASE_ID)",)
MODEL_ARG := $(if $(MODEL),--model "$(MODEL)",)

.PHONY: help debug batch openai groq gemini anthropic

help:
	@printf "Available targets:\n"
	@printf "  make debug CASE_ID=...     Run one case; stdout + JSON in results/\n"
	@printf "  make batch                 Run cases across MODELS\n"
	@printf "  make openai CASE_ID=...    Debug with OpenAI only\n"
	@printf "  make groq CASE_ID=...      Debug with Groq only\n"
	@printf "  make gemini CASE_ID=...    Debug with Gemini on Vertex AI\n"
	@printf "  make anthropic CASE_ID=... Debug with Anthropic API\n"
	@printf "\n"
	@printf "Configurable variables:\n"
	@printf "  CASES=%s\n" "$(CASES)"
	@printf "  CASE_ID=%s\n" "$(CASE_ID)"
	@printf "  COUNT=%s\n" "$(COUNT)"
	@printf "  LAST=%s\n" "$(LAST)"
	@printf "  MODELS=%s\n" "$(MODELS)"
	@printf "  PROVIDER=%s\n" "$(PROVIDER)"
	@printf "  MODEL=%s\n" "$(MODEL)"
	@printf "  OPENAI_MODEL=%s\n" "$(OPENAI_MODEL)"
	@printf "  GROQ_MODEL=%s\n" "$(GROQ_MODEL)"
	@printf "  GEMINI_MODEL=%s\n" "$(GEMINI_MODEL)"
	@printf "  ANTHROPIC_MODEL=%s\n" "$(ANTHROPIC_MODEL)"
	@printf "  PROMPT_VERSION=%s\n" "$(PROMPT_VERSION)"
	@printf "  OUTPUT_DETAIL=%s\n" "$(OUTPUT_DETAIL)"
	@printf "  RESULTS_DIR=%s\n" "$(RESULTS_DIR)"
	@printf "\n"
	@printf "Examples:\n"
	@printf "  make debug CASE_ID=medication_question_and_avoid PROVIDER=openai\n"
	@printf "  make batch MODELS=openai:$(OPENAI_MODEL),groq:$(GROQ_MODEL)\n"
	@printf "  make batch CASE_ID=eval_doc_clinica_co_001 LAST=1\n"

debug:
	@if [ -z "$(CASE_ID)" ]; then echo "Usage: make debug CASE_ID=case_id"; exit 1; fi
	$(PYTHON) run_debug.py \
		--cases "$(CASES)" \
		--case-id "$(CASE_ID)" \
		--provider "$(PROVIDER)" \
		--prompt-version "$(PROMPT_VERSION)" \
		--results-dir "$(RESULTS_DIR)" \
		--output-detail "$(OUTPUT_DETAIL)" \
		$(MODEL_ARG)

batch:
	$(PYTHON) run_batch.py \
		--cases "$(CASES)" \
		--models "$(MODELS)" \
		--prompt-version "$(PROMPT_VERSION)" \
		--output-detail "$(OUTPUT_DETAIL)" \
		--results-dir "$(RESULTS_DIR)" \
		$(CASE_ARGS)

openai:
	$(MAKE) debug PROVIDER=openai MODEL="$(if $(MODEL),$(MODEL),$(OPENAI_MODEL))"

groq:
	$(MAKE) debug PROVIDER=groq MODEL="$(if $(MODEL),$(MODEL),$(GROQ_MODEL))"

gemini:
	$(MAKE) debug PROVIDER=gemini MODEL="$(if $(MODEL),$(MODEL),$(GEMINI_MODEL))"

anthropic:
	$(MAKE) debug PROVIDER=anthropic MODEL="$(if $(MODEL),$(MODEL),$(ANTHROPIC_MODEL))"
