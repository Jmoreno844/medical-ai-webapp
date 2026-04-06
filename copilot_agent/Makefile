PYTEST ?= uv run pytest
LANGSMITH_EXPERIMENT ?= planner-drafter-local
LANGSMITH_TEST_SUITE ?= copilot-agent-local-live
MODEL ?=
COUNT ?=
EXACT ?=
EVAL_CASE_SELECTION_ENV = $(if $(EXACT),EVAL_CASE_EXACT=$(EXACT),$(if $(COUNT),EVAL_CASE_LIMIT=$(COUNT),))
REASONING_CASE_SELECTION_ENV = $(if $(EXACT),REASONING_CASE_EXACT=$(EXACT),$(if $(COUNT),REASONING_CASE_LIMIT=$(COUNT),))
GEMINI_25_REGION ?= us-east1
GEMINI_PREVIEW_REGION ?= global

.DEFAULT_GOAL := help

.PHONY: help evals-live evals-live-no-track evals-smoke evals-e2e evals-e2e-model evals-e2e-gemini-2-5 evals-e2e-gemini-preview evals-e2e-openai evals-e2e-anthropic evals-reasoning

help:
	@printf "Available targets:\n"
	@printf "  make evals-live              Run live LangSmith planner+drafter evals (default model)\n"
	@printf "  make evals-live-no-track     Run live evals without sending results to LangSmith\n"
	@printf "  make evals-smoke             Run one-call-per-model smoke checks\n"
	@printf "\n"
	@printf "  Optional: append COUNT=5|10|15 to any e2e target to run only the first N cases\n"
	@printf "  Optional: append EXACT=3 to any e2e target to run only case #3 (1-based, overrides COUNT)\n"
	@printf "           For exactly one pytest case, combine EXACT with MODEL, e.g. make evals-e2e-model MODEL=openai-gpt-5.4-mini EXACT=3\n"
	@printf "  make evals-reasoning         Qualitative planner reasoning comparison (Gemini 3 preview vs Haiku 4.5 vs GPT-4 mini)\n"
	@printf "  make evals-e2e               Full pipeline across all 7 providers in the matrix\n"
	@printf "  make evals-e2e-model MODEL=x Run pipeline for one provider id (e.g. google-gemini-2.5-flash)\n"
	@printf "  make evals-e2e-gemini-2-5    Pipeline for gemini-2.5 flash + flash-lite (region $(GEMINI_25_REGION))\n"
	@printf "  make evals-e2e-gemini-preview Pipeline for gemini-3 flash preview + 3.1 flash-lite preview (region $(GEMINI_PREVIEW_REGION))\n"
	@printf "  make evals-e2e-openai        Pipeline for openai providers only\n"
	@printf "  make evals-e2e-anthropic     Pipeline for anthropic providers only\n"

evals-live:
	LANGSMITH_TRACING=true LANGSMITH_TEST_TRACKING=true LANGSMITH_EXPERIMENT=$(LANGSMITH_EXPERIMENT) LANGSMITH_TEST_SUITE=$(LANGSMITH_TEST_SUITE) $(PYTEST) -m live_llm evals/langsmith -q --ignore=evals/langsmith/test_live_e2e_pipeline.py

evals-live-no-track:
	LANGSMITH_EXPERIMENT=$(LANGSMITH_EXPERIMENT) LANGSMITH_TEST_SUITE=$(LANGSMITH_TEST_SUITE) LANGSMITH_TEST_TRACKING=false $(PYTEST) -m live_llm evals/langsmith -q --ignore=evals/langsmith/test_live_e2e_pipeline.py

evals-smoke:
	$(PYTEST) -m live_llm evals/langsmith/test_provider_model_smoke.py -q -rs

evals-reasoning:
	$(REASONING_CASE_SELECTION_ENV) LANGSMITH_TRACING=true LANGSMITH_TEST_TRACKING=true LANGSMITH_EXPERIMENT=clinical-reasoning-$(shell date +%Y%m%d) LANGSMITH_TEST_SUITE=$(LANGSMITH_TEST_SUITE) $(PYTEST) -m live_llm evals/langsmith/test_live_clinical_reasoning.py -q -v

evals-e2e:
	$(EVAL_CASE_SELECTION_ENV) LANGSMITH_TRACING=true LANGSMITH_TEST_TRACKING=true LANGSMITH_EXPERIMENT=e2e-pipeline-$(shell date +%Y%m%d) LANGSMITH_TEST_SUITE=$(LANGSMITH_TEST_SUITE) $(PYTEST) -m live_llm evals/langsmith/test_live_e2e_pipeline.py -q -v

evals-e2e-model:
	@if [ -z "$(MODEL)" ]; then echo "Usage: make evals-e2e-model MODEL=google-gemini-2.5-flash EXACT=3"; exit 1; fi
	$(EVAL_CASE_SELECTION_ENV) LANGSMITH_TRACING=true LANGSMITH_TEST_TRACKING=true LANGSMITH_EXPERIMENT=e2e-$(MODEL)-$(shell date +%Y%m%d) LANGSMITH_TEST_SUITE=$(LANGSMITH_TEST_SUITE) $(PYTEST) -m live_llm evals/langsmith/test_live_e2e_pipeline.py -k "$(MODEL)" -q -v

evals-e2e-gemini-2-5:
	$(EVAL_CASE_SELECTION_ENV) GCP_REGION=$(GEMINI_25_REGION) LANGSMITH_TRACING=true LANGSMITH_TEST_TRACKING=true LANGSMITH_EXPERIMENT=e2e-gemini-2.5-$(shell date +%Y%m%d) LANGSMITH_TEST_SUITE=$(LANGSMITH_TEST_SUITE) $(PYTEST) -m live_llm evals/langsmith/test_live_e2e_pipeline.py -k "google-gemini-2.5" -q -v

evals-e2e-gemini-preview:
	$(EVAL_CASE_SELECTION_ENV) GCP_REGION=$(GEMINI_PREVIEW_REGION) LANGSMITH_TRACING=true LANGSMITH_TEST_TRACKING=true LANGSMITH_EXPERIMENT=e2e-gemini-preview-$(shell date +%Y%m%d) LANGSMITH_TEST_SUITE=$(LANGSMITH_TEST_SUITE) $(PYTEST) -m live_llm evals/langsmith/test_live_e2e_pipeline.py -k "google-gemini-3" -q -v

evals-e2e-openai:
	$(EVAL_CASE_SELECTION_ENV) LANGSMITH_TRACING=true LANGSMITH_TEST_TRACKING=true LANGSMITH_EXPERIMENT=e2e-openai-$(shell date +%Y%m%d) LANGSMITH_TEST_SUITE=$(LANGSMITH_TEST_SUITE) $(PYTEST) -m live_llm evals/langsmith/test_live_e2e_pipeline.py -k "openai" -q -v

evals-e2e-anthropic:
	$(EVAL_CASE_SELECTION_ENV) LANGSMITH_TRACING=true LANGSMITH_TEST_TRACKING=true LANGSMITH_EXPERIMENT=e2e-anthropic-$(shell date +%Y%m%d) LANGSMITH_TEST_SUITE=$(LANGSMITH_TEST_SUITE) $(PYTEST) -m live_llm evals/langsmith/test_live_e2e_pipeline.py -k "anthropic" -q -v