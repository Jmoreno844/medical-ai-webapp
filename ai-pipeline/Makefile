.DEFAULT_GOAL := help

.PHONY: help sync sync-ui ui test lint

help:
	@printf "AI Pipeline harness\n\n"
	@printf "  make sync      Install runtime + dev deps (pytest, ruff)\n"
	@printf "  make sync-ui   Install runtime + dev + streamlit (required for UI)\n"
	@printf "  make ui        Run Streamlit app (uses uv venv)\n"
	@printf "  make test      Run pytest\n"
	@printf "  make lint      Run ruff\n\n"
	@printf "Always use 'make ui' or 'uv run streamlit ...' — not bare 'streamlit'.\n"

sync:
	uv sync --group dev

sync-ui:
	uv sync --group dev --group ui

ui: sync-ui
	uv run streamlit run ui/app.py

test:
	uv run pytest -q

lint:
	uv run ruff check .
