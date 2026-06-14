from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from common.context_spans import (
    Directive,
    FilterSpansResult,
    Span,
    audit_filter_spans_result,
    span_to_payload_item,
)
from common.json_utils import extract_json_object
from common.prompts import load_prompt as load_prompt_from_file
from common.prompts import prompt_file_path as resolve_prompt_file_path

MODULE_ROOT = Path(__file__).resolve().parent
PROMPTS_DIR = MODULE_ROOT / "prompts"
PROMPT_FILENAME_STEM = "filter_spans"


def filter_spans_prompt_file_path(version: str) -> Path:
    return resolve_prompt_file_path(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def load_filter_spans_prompt(version: str) -> str:
    return load_prompt_from_file(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def prompt_file_path(version: str) -> Path:
    return filter_spans_prompt_file_path(version)


def load_prompt(version: str) -> str:
    return load_filter_spans_prompt(version)


def render_filter_spans_payload(
    *,
    encounter_date: str | None,
    document_date: str | None,
    directives: list[Directive],
    spans: list[Span],
) -> str:
    if not spans:
        raise ValueError("filter_spans_payload_requires_at_least_one_span")
    payload = {
        "encounter_date": encounter_date,
        "document_date": document_date,
        "directives": [directive.model_dump(mode="json") for directive in directives],
        "spans": [span_to_payload_item(span) for span in spans],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def parse_filter_spans_result(raw: str) -> FilterSpansResult:
    payload = extract_json_object(raw)
    try:
        return FilterSpansResult.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"filter_spans_invalid_result: {exc}") from exc


def enrich_filter_spans_result_for_export(
    result: FilterSpansResult,
    *,
    spans: list[Span],
) -> dict[str, object]:
    drop_set = set(result.drop_ids)
    return {
        "drop_ids": list(result.drop_ids),
        "drop_count": len(result.drop_ids),
        "kept_span_count": sum(1 for span in spans if span.id not in drop_set),
    }


__all__ = [
    "MODULE_ROOT",
    "audit_filter_spans_result",
    "enrich_filter_spans_result_for_export",
    "load_filter_spans_prompt",
    "load_prompt",
    "parse_filter_spans_result",
    "prompt_file_path",
    "render_filter_spans_payload",
]
