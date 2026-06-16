from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from common.context_spans import (
    AmbiguousDirective,
    Directive,
    Span,
    SpanSelectorResult,
    audit_span_selector_result,
    document_filter_directives,
    resolve_document_target,
    span_to_payload_item,
)
from common.json_utils import extract_json_object
from common.prompt_registry import is_py_prompt_version, load_py_prompt_module, py_system_prompt
from common.prompts import load_prompt as load_prompt_from_file
from common.prompts import prompt_file_path as resolve_prompt_file_path

MODULE_ROOT = Path(__file__).resolve().parent
PROMPTS_DIR = MODULE_ROOT / "prompts"
PROMPT_FILENAME_STEM = "span_selector"
PY_SPAN_SELECTOR_STEP = "context_document_directive_filter"
PY_SPAN_SELECTOR_PROMPT_VERSIONS = frozenset({"v001"})


@dataclass(frozen=True, slots=True)
class DocumentDirectiveFilterOutcome:
    spans: list[Span]
    ambiguous_directives: list[AmbiguousDirective] = field(default_factory=list)
    selector_results: list[SpanSelectorResult] = field(default_factory=list)


def span_selector_uses_py_prompt(prompt_version: str) -> bool:
    return is_py_prompt_version(PY_SPAN_SELECTOR_STEP, prompt_version)


def span_selector_structured_output_enabled(prompt_version: str) -> bool:
    return prompt_version.strip().lower() in PY_SPAN_SELECTOR_PROMPT_VERSIONS


def span_selector_output_schema(
    spans: list[Span],
    *,
    prompt_version: str,
) -> dict[str, object] | None:
    if not span_selector_structured_output_enabled(prompt_version):
        return None
    module = load_py_prompt_module(PY_SPAN_SELECTOR_STEP, prompt_version)
    output_schema_fn = getattr(module, "output_schema", None)
    if not callable(output_schema_fn):
        raise ValueError(
            f"document_directive_filter_py_prompt_missing_output_schema: {prompt_version}"
        )
    schema = output_schema_fn(span_ids=[span.id for span in spans])
    if not isinstance(schema, dict):
        raise ValueError(
            f"document_directive_filter_py_prompt_invalid_output_schema: {prompt_version}"
        )
    return schema


def span_selector_prompt_file_path(version: str) -> Path:
    return resolve_prompt_file_path(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def load_span_selector_prompt(version: str) -> str:
    if span_selector_uses_py_prompt(version):
        return py_system_prompt(PY_SPAN_SELECTOR_STEP, version)
    return load_prompt_from_file(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def render_span_selector_payload(
    *,
    directive: Directive,
    spans: list[Span],
    prompt_version: str = "v001",
) -> str:
    if not spans:
        raise ValueError("span_selector_payload_requires_at_least_one_span")
    directive_payload = directive.model_dump(mode="json")
    spans_payload = [span_to_payload_item(span) for span in spans]
    if span_selector_uses_py_prompt(prompt_version):
        module = load_py_prompt_module(PY_SPAN_SELECTOR_STEP, prompt_version)
        return module.render_user_payload(
            directive=directive_payload,
            spans=spans_payload,
        )
    payload = {
        "directive": directive_payload,
        "spans": spans_payload,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def parse_span_selector_result(raw: str) -> SpanSelectorResult:
    payload = extract_json_object(raw)
    try:
        return SpanSelectorResult.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"span_selector_invalid_result: {exc}") from exc


def _candidate_spans_for_directive(
    spans: list[Span],
    *,
    resolved_target: str,
) -> list[Span]:
    if resolved_target == "__all__":
        return list(spans)
    return [span for span in spans if span.doc == resolved_target]


def _apply_keep_ids_to_spans(
    spans: list[Span],
    *,
    candidate_spans: list[Span],
    keep_ids: set[str],
) -> list[Span]:
    candidate_ids = {span.id for span in candidate_spans}
    return [
        span
        for span in spans
        if span.id not in candidate_ids or span.id in keep_ids
    ]


def apply_ignore_source_directives(
    spans: list[Span],
    directives: list[Directive],
    *,
    available_documents: list[str],
) -> tuple[list[Span], list[AmbiguousDirective]]:
    current = list(spans)
    ambiguous: list[AmbiguousDirective] = []

    for directive in document_filter_directives(directives):
        if directive.action != "ignore_source":
            continue
        resolved_target = resolve_document_target(directive.target, available_documents)
        if resolved_target is None:
            ambiguous.append(
                AmbiguousDirective(
                    directive=directive,
                    reason="unresolved_document_target",
                )
            )
            continue
        if resolved_target == "__all__":
            current = []
        else:
            current = [span for span in current if span.doc != resolved_target]

    return current, ambiguous


def apply_document_directives(
    spans: list[Span],
    directives: list[Directive],
    *,
    available_documents: list[str],
    selector_results: list[SpanSelectorResult] | None = None,
) -> DocumentDirectiveFilterOutcome:
    current, ambiguous = apply_ignore_source_directives(
        spans,
        directives,
        available_documents=available_documents,
    )
    collected_selector_results: list[SpanSelectorResult] = []
    pending_selector_results = list(selector_results or [])

    for directive in document_filter_directives(directives):
        if directive.action == "ignore_source":
            continue

        resolved_target = resolve_document_target(directive.target, available_documents)
        if resolved_target is None:
            ambiguous.append(
                AmbiguousDirective(
                    directive=directive,
                    reason="unresolved_document_target",
                )
            )
            continue

        candidate_spans = _candidate_spans_for_directive(
            current,
            resolved_target=resolved_target,
        )
        if not candidate_spans:
            continue

        if not pending_selector_results:
            ambiguous.append(
                AmbiguousDirective(
                    directive=directive,
                    reason="missing_selector_result",
                )
            )
            continue

        selector_result = pending_selector_results.pop(0)
        audit_span_selector_result(candidate_spans, selector_result)
        collected_selector_results.append(selector_result)
        current = _apply_keep_ids_to_spans(
            current,
            candidate_spans=candidate_spans,
            keep_ids=set(selector_result.keep_ids),
        )

    return DocumentDirectiveFilterOutcome(
        spans=current,
        ambiguous_directives=ambiguous,
        selector_results=collected_selector_results,
    )


__all__ = [
    "DocumentDirectiveFilterOutcome",
    "apply_document_directives",
    "apply_ignore_source_directives",
    "load_span_selector_prompt",
    "parse_span_selector_result",
    "render_span_selector_payload",
    "span_selector_output_schema",
    "span_selector_prompt_file_path",
    "span_selector_structured_output_enabled",
    "span_selector_uses_py_prompt",
]
