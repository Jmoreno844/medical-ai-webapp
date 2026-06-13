.DEFAULT_GOAL := help
-include .env.local

PYTHON ?= uv --project ../.. run python
CASES ?= ../cases/index.json
RESULTS_DIR ?= results
PROMPT_VERSION ?= v001
OUTPUT_DETAIL ?= compact
OPENAI_MODEL ?= gpt-5.4-mini
PROVIDER ?= openai
MODEL ?=
CASE_ID ?=
DECOMPOSE_RESULT ?=
EXTRACT_RESULT ?=
CLAIMS_JSON ?=
TEMPLATE_ID ?=
MODEL_ARG := $(if $(MODEL),--model "$(MODEL)",)
DEC_ARG := $(if $(DECOMPOSE_RESULT),--decompose-result "$(DECOMPOSE_RESULT)",)
EXT_ARG := $(if $(EXTRACT_RESULT),--extract-result "$(EXTRACT_RESULT)",)
CLAIMS_ARG := $(if $(CLAIMS_JSON),--claims-json "$(CLAIMS_JSON)",)
TEMPLATE_ARG := $(if $(TEMPLATE_ID),--template-id "$(TEMPLATE_ID)",)

.PHONY: help debug-session openai

help:
	@printf "  make debug-session CASE_ID=case1 DECOMPOSE_RESULT=... EXTRACT_RESULT=...\n"

debug-session:
	@if [ -z "$(CASE_ID)" ]; then echo "Usage: make debug-session CASE_ID=case1"; exit 1; fi
	$(PYTHON) run_debug_session.py \
		--cases "$(CASES)" \
		--case-id "$(CASE_ID)" \
		--provider "$(PROVIDER)" \
		--prompt-version "$(PROMPT_VERSION)" \
		--results-dir "$(RESULTS_DIR)" \
		--output-detail "$(OUTPUT_DETAIL)" \
		$(MODEL_ARG) \
		$(DEC_ARG) \
		$(EXT_ARG) \
		$(CLAIMS_ARG) \
		$(TEMPLATE_ARG)

openai:
	$(MAKE) debug-session PROVIDER=openai MODEL="$(if $(MODEL),$(MODEL),$(OPENAI_MODEL))"
