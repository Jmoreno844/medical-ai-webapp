from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from document_pipeline_core.common.context_spans import (
    Directive,
    FilterSpansResult,
    Span,
    audit_filter_spans_result,
    span_to_payload_item,
)
from document_pipeline_core.common.json_utils import extract_json_object
from document_pipeline_core.common.prompt_registry import is_py_prompt_version, load_py_prompt_module, py_system_prompt
from document_pipeline_core.common.prompts import load_prompt as load_prompt_from_file
from document_pipeline_core.common.prompts import prompt_file_path as resolve_prompt_file_path

MODULE_ROOT = Path(__file__).resolve().parent
PROMPTS_DIR = MODULE_ROOT / "prompts"
PROMPT_FILENAME_STEM = "filter_spans"
PY_FILTER_SPANS_STEP = "context_filter_spans"
PY_FILTER_SPANS_PROMPT_VERSIONS = frozenset({"v002"})


def filter_spans_uses_py_prompt(prompt_version: str) -> bool:
    return is_py_prompt_version(PY_FILTER_SPANS_STEP, prompt_version)


def filter_spans_structured_output_enabled(prompt_version: str) -> bool:
    return prompt_version.strip().lower() in PY_FILTER_SPANS_PROMPT_VERSIONS


def filter_spans_output_schema(
    spans: list[Span],
    *,
    prompt_version: str,
) -> dict[str, object] | None:
    if not filter_spans_structured_output_enabled(prompt_version):
        return None
    module = load_py_prompt_module(PY_FILTER_SPANS_STEP, prompt_version)
    output_schema_fn = getattr(module, "output_schema", None)
    if not callable(output_schema_fn):
        raise ValueError(f"filter_spans_py_prompt_missing_output_schema: {prompt_version}")
    span_ids = [span.id for span in spans]
    schema = output_schema_fn(span_ids=span_ids)
    if not isinstance(schema, dict):
        raise ValueError(f"filter_spans_py_prompt_invalid_output_schema: {prompt_version}")
    return schema


def filter_spans_prompt_file_path(version: str) -> Path:
    return resolve_prompt_file_path(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def load_filter_spans_prompt(version: str) -> str:
    if filter_spans_uses_py_prompt(version):
        return py_system_prompt(PY_FILTER_SPANS_STEP, version)
    return load_prompt_from_file(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def filter_spans_prompt_reference(version: str) -> str:
    if filter_spans_uses_py_prompt(version):
        module_path = load_py_prompt_module(PY_FILTER_SPANS_STEP, version).__name__
        return f"{module_path.replace('.', '/')}.py"
    return str(filter_spans_prompt_file_path(version).relative_to(MODULE_ROOT))


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
    prompt_version: str = "v001",
) -> str:
    if not spans:
        raise ValueError("filter_spans_payload_requires_at_least_one_span")
    directives_payload = [directive.model_dump(mode="json") for directive in directives]
    spans_payload = [span_to_payload_item(span) for span in spans]
    if filter_spans_uses_py_prompt(prompt_version):
        module = load_py_prompt_module(PY_FILTER_SPANS_STEP, prompt_version)
        return module.render_user_payload(
            encounter_date=encounter_date,
            document_date=document_date,
            directives=directives_payload,
            spans=spans_payload,
        )
    return json.dumps(
        {
            "encounter_date": encounter_date,
            "document_date": document_date,
            "directives": directives_payload,
            "spans": spans_payload,
        },
        ensure_ascii=False,
        indent=2,
    )


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
    "filter_spans_output_schema",
    "filter_spans_prompt_file_path",
    "filter_spans_prompt_reference",
    "filter_spans_structured_output_enabled",
    "filter_spans_uses_py_prompt",
    "load_filter_spans_prompt",
    "load_prompt",
    "parse_filter_spans_result",
    "prompt_file_path",
    "render_filter_spans_payload",
]
