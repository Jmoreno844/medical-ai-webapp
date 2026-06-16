from __future__ import annotations

from document_pipeline_core.generation.evidence_markers import extract_all_marker_ids, strip_evidence_markers

TWO_STEP_ROUTE = "two_step"
PLANNER_STEP = "planner"
RENDERER_STEP = "renderer"
CONTENT_VIEW_APPLIED = "Markdown aplicado"
CONTENT_VIEW_SOURCE = "Markdown fuente"


def section_generation_route(section_output: dict[str, object] | None) -> str | None:
    if section_output is None:
        return None
    route = section_output.get("generation_route")
    if isinstance(route, str) and route.strip():
        return route.strip()
    return None


def is_two_step_section_output(section_output: dict[str, object] | None) -> bool:
    return section_generation_route(section_output) == TWO_STEP_ROUTE


def has_linked_evidence_audit_data(section_output: dict[str, object] | None) -> bool:
    if not is_two_step_section_output(section_output):
        return False
    planner_items = section_output.get("planner_items")
    draft = section_output.get("draft_with_evidence")
    llm_responses = section_output.get("llm_responses")
    has_items = isinstance(planner_items, list) and bool(planner_items)
    has_draft = isinstance(draft, str) and bool(draft.strip())
    has_calls = isinstance(llm_responses, list) and bool(llm_responses)
    return has_items or has_draft or has_calls


def is_legacy_two_step_section(section_output: dict[str, object] | None) -> bool:
    return is_two_step_section_output(section_output) and not has_linked_evidence_audit_data(
        section_output
    )


def resolve_llm_response_by_step(
    llm_responses: object,
    *,
    step: str,
) -> dict[str, object] | None:
    if not isinstance(llm_responses, list):
        return None

    for item in llm_responses:
        if isinstance(item, dict) and item.get("step") == step:
            return item

    if not llm_responses:
        return None

    fallback_index = {"planner": 0, "renderer": 1}.get(step)
    if fallback_index is None or fallback_index >= len(llm_responses):
        return None

    fallback = llm_responses[fallback_index]
    if isinstance(fallback, dict) and "step" not in fallback:
        return fallback
    return None


def format_cited_evidence_ids_caption(text: str) -> str:
    cited_ids = sorted(extract_all_marker_ids(text))
    if not cited_ids:
        return ""
    return f"IDs citados: {', '.join(cited_ids)}"


def display_generation_content(
    content: str,
    *,
    content_view_mode: str = CONTENT_VIEW_APPLIED,
    show_evidence_ids: bool = False,
) -> str:
    if content_view_mode == CONTENT_VIEW_SOURCE:
        return content
    if show_evidence_ids:
        return content
    return strip_evidence_markers(content)


def planner_raw_output(section_output: dict[str, object] | None) -> str:
    if section_output is None:
        return ""
    planner_call = resolve_llm_response_by_step(
        section_output.get("llm_responses"),
        step=PLANNER_STEP,
    )
    if planner_call is None:
        return ""
    content = planner_call.get("content")
    return content if isinstance(content, str) else ""


__all__ = [
    "CONTENT_VIEW_APPLIED",
    "CONTENT_VIEW_SOURCE",
    "PLANNER_STEP",
    "RENDERER_STEP",
    "TWO_STEP_ROUTE",
    "display_generation_content",
    "format_cited_evidence_ids_caption",
    "has_linked_evidence_audit_data",
    "is_legacy_two_step_section",
    "is_two_step_section_output",
    "planner_raw_output",
    "resolve_llm_response_by_step",
    "section_generation_route",
]
