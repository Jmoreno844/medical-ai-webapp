.DEFAULT_GOAL := help
-include .env.local

PYTHON ?= uv --project .. run python
CASES ?= ../classification/cases/index.json
TEMPLATES_DIR ?= ../templates
RESULTS_DIR ?= results
PROMPT_VERSION ?= v001
OUTPUT_DETAIL ?= compact
SECTION_CONCURRENCY ?= 0
OPENAI_MODEL ?= gpt-5.4-mini
GROQ_MODEL ?= qwen/qwen3-32b
GEMINI_MODEL ?= gemini-3-flash-preview
ANTHROPIC_MODEL ?= claude-haiku-4-5-20251001
PROVIDER ?= openai
MODEL ?=
TEMPLATE_ID ?=
SESSION_ID ?=
SECTION_ID ?=
CLASSIFICATION_RESULT ?=
CLAIM_CLASSIFICATION_RESULT ?=
MODEL_ARG := $(if $(MODEL),--model "$(MODEL)",)
TEMPLATE_ARG := $(if $(TEMPLATE_ID),--template-id "$(TEMPLATE_ID)",)
CLAIM_ARG := $(if $(CLAIM_CLASSIFICATION_RESULT),--claim-classification-result "$(CLAIM_CLASSIFICATION_RESULT)",)

.PHONY: help debug debug-session openai groq gemini anthropic

help:
	@printf "Available targets:\n"
	@printf "  make debug-session SESSION_ID=... CLASSIFICATION_RESULT=...\n"
	@printf "  make debug SESSION_ID=... SECTION_ID=... CLASSIFICATION_RESULT=...\n"
	@printf "  make openai / groq / gemini / anthropic\n"
	@printf "\n"
	@printf "Configurable variables:\n"
	@printf "  CASES=%s\n" "$(CASES)"
	@printf "  SESSION_ID=%s\n" "$(SESSION_ID)"
	@printf "  SECTION_ID=%s\n" "$(SECTION_ID)"
	@printf "  CLASSIFICATION_RESULT=%s\n" "$(CLASSIFICATION_RESULT)"
	@printf "  TEMPLATES_DIR=%s\n" "$(TEMPLATES_DIR)"
	@printf "  SECTION_CONCURRENCY=%s\n" "$(SECTION_CONCURRENCY)"
	@printf "  PROVIDER=%s\n" "$(PROVIDER)"
	@printf "  PROMPT_VERSION=%s\n" "$(PROMPT_VERSION)"
	@printf "  OUTPUT_DETAIL=%s\n" "$(OUTPUT_DETAIL)"
	@printf "\n"
	@printf "Examples:\n"
	@printf "  make debug-session SESSION_ID=case1 CLASSIFICATION_RESULT=../classification/results/20260612T222321Z_session_case1_groq.json PROVIDER=openai\n"
	@printf "  make debug SESSION_ID=case1 SECTION_ID=enfermedad_actual CLASSIFICATION_RESULT=../classification/results/20260612T222321Z_session_case1_groq.json\n"

debug-session:
	@if [ -z "$(SESSION_ID)" ]; then echo "Usage: make debug-session SESSION_ID=case1 CLASSIFICATION_RESULT=..."; exit 1; fi
	@if [ -z "$(CLASSIFICATION_RESULT)" ]; then echo "Usage: make debug-session SESSION_ID=case1 CLASSIFICATION_RESULT=..."; exit 1; fi
	$(PYTHON) run_debug_session.py \
		--cases "$(CASES)" \
		--session-id "$(SESSION_ID)" \
		--classification-result "$(CLASSIFICATION_RESULT)" \
		--templates-dir "$(TEMPLATES_DIR)" \
		--section-concurrency "$(SECTION_CONCURRENCY)" \
		--provider "$(PROVIDER)" \
		--prompt-version "$(PROMPT_VERSION)" \
		--results-dir "$(RESULTS_DIR)" \
		--output-detail "$(OUTPUT_DETAIL)" \
		$(MODEL_ARG) \
		$(TEMPLATE_ARG) \
		$(CLAIM_ARG)

debug:
	@if [ -z "$(SESSION_ID)" ]; then echo "Usage: make debug SESSION_ID=case1 SECTION_ID=... CLASSIFICATION_RESULT=..."; exit 1; fi
	@if [ -z "$(SECTION_ID)" ]; then echo "Usage: make debug SESSION_ID=case1 SECTION_ID=... CLASSIFICATION_RESULT=..."; exit 1; fi
	@if [ -z "$(CLASSIFICATION_RESULT)" ]; then echo "Usage: make debug SESSION_ID=case1 SECTION_ID=... CLASSIFICATION_RESULT=..."; exit 1; fi
	$(PYTHON) run_debug.py \
		--cases "$(CASES)" \
		--session-id "$(SESSION_ID)" \
		--section-id "$(SECTION_ID)" \
		--classification-result "$(CLASSIFICATION_RESULT)" \
		--templates-dir "$(TEMPLATES_DIR)" \
		--provider "$(PROVIDER)" \
		--prompt-version "$(PROMPT_VERSION)" \
		--results-dir "$(RESULTS_DIR)" \
		--output-detail "$(OUTPUT_DETAIL)" \
		$(MODEL_ARG) \
		$(TEMPLATE_ARG) \
		$(CLAIM_ARG)

openai:
	$(MAKE) debug-session PROVIDER=openai MODEL="$(if $(MODEL),$(MODEL),$(OPENAI_MODEL))"

groq:
	$(MAKE) debug-session PROVIDER=groq MODEL="$(if $(MODEL),$(MODEL),$(GROQ_MODEL))"

gemini:
	$(MAKE) debug-session PROVIDER=gemini MODEL="$(if $(MODEL),$(MODEL),$(GEMINI_MODEL))"

anthropic:
	$(MAKE) debug-session PROVIDER=anthropic MODEL="$(if $(MODEL),$(MODEL),$(ANTHROPIC_MODEL))"
