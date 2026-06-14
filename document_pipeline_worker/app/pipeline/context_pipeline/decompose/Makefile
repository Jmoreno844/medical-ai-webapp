.DEFAULT_GOAL := help
-include .env.local

PYTHON ?= uv --project ../.. run python
CASES ?= ../cases/context/index.json
RESULTS_DIR ?= results
PROMPT_VERSION ?= v001
OUTPUT_DETAIL ?= compact
OPENAI_MODEL ?= gpt-5.4-mini
PROVIDER ?= openai
MODEL ?=
CASE_ID ?=
MODEL_ARG := $(if $(MODEL),--model "$(MODEL)",)

.PHONY: help debug openai

help:
	@printf "  make debug CASE_ID=case1 PROVIDER=openai\n"

debug:
	@if [ -z "$(CASE_ID)" ]; then echo "Usage: make debug CASE_ID=case1"; exit 1; fi
	$(PYTHON) run_debug.py \
		--cases "$(CASES)" \
		--case-id "$(CASE_ID)" \
		--provider "$(PROVIDER)" \
		--prompt-version "$(PROMPT_VERSION)" \
		--results-dir "$(RESULTS_DIR)" \
		--output-detail "$(OUTPUT_DETAIL)" \
		$(MODEL_ARG)

openai:
	$(MAKE) debug PROVIDER=openai MODEL="$(if $(MODEL),$(MODEL),$(OPENAI_MODEL))"
