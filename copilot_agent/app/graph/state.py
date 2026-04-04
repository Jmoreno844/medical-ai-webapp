from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import Annotated

# RESET_MARKER signals list/dict reducers to discard the accumulated value from
# the prior checkpoint and start fresh. Without this, tool reads, spans, and
# proposals from a previous run would bleed into the next run on the same thread.
# LangGraph checkpoints are thread-scoped, so there is no automatic per-run flush.
RESET_MARKER = "__reset__"


def reset_list_state() -> list[dict[str, Any]]:
    return [{RESET_MARKER: True}]


def reset_dict_state() -> dict[str, Any]:
    return {RESET_MARKER: True}


def materialize_state_value(value: Any) -> Any:
    if isinstance(value, dict) and value.get(RESET_MARKER) is True:
        return {}
    if (
        isinstance(value, list)
        and value
        and isinstance(value[0], dict)
        and value[0].get(RESET_MARKER) is True
    ):
        return []
    return value


def materialize_state_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    return {
        key: materialize_state_value(value)
        for key, value in state.items()
    }


def _split_list_reset(
    current: list[dict[str, Any]] | None,
    updates: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if updates and isinstance(updates[0], dict) and updates[0].get(RESET_MARKER) is True:
        return [], list(updates[1:])
    return list(current or []), list(updates or [])


def _split_dict_reset(
    current: dict[str, Any] | None,
    updates: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if updates and updates.get(RESET_MARKER) is True:
        return {}, {key: value for key, value in updates.items() if key != RESET_MARKER}
    return dict(current or {}), dict(updates or {})


def _append_items(
    current: list[dict[str, Any]] | None,
    updates: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    base, delta = _split_list_reset(current, updates)
    return [*base, *delta]


def _truthy_score(value: Any) -> int:
    return 1 if value not in (None, "", [], {}, False) else 0


def _document_score(document: dict[str, Any]) -> tuple[int, ...]:
    return (
        1 if document.get("is_active") else 0,
        1 if document.get("pinned_for_agent") else 0,
        1 if document.get("is_open") else 0,
        1 if document.get("ai_writable") else 0,
        _truthy_score(document.get("excerpt")),
        _truthy_score(document.get("updated_at")),
        _truthy_score(document.get("title")),
        _truthy_score(document.get("type")),
        _truthy_score(document.get("status")),
        _truthy_score(document.get("source")),
        int(document.get("version") or 0),
    )


def _merge_document_pair(
    existing: dict[str, Any],
    incoming: dict[str, Any],
) -> dict[str, Any]:
    preferred, fallback = sorted(
        [existing, incoming],
        key=_document_score,
        reverse=True,
    )[:2]
    merged = {**preferred}
    merged["document_id"] = str(preferred.get("document_id") or fallback.get("document_id") or "")
    merged["is_active"] = bool(existing.get("is_active")) or bool(incoming.get("is_active"))
    merged["is_open"] = bool(existing.get("is_open")) or bool(incoming.get("is_open"))
    merged["pinned_for_agent"] = bool(existing.get("pinned_for_agent")) or bool(
        incoming.get("pinned_for_agent")
    )
    merged["ai_writable"] = bool(existing.get("ai_writable")) or bool(incoming.get("ai_writable"))
    merged["version"] = max(int(existing.get("version") or 0), int(incoming.get("version") or 0)) or None

    for field_name in ("title", "type", "status", "source", "updated_at", "excerpt"):
        merged[field_name] = preferred.get(field_name) or fallback.get(field_name)

    return merged


# Score-based merge instead of last-write-wins: list_encounter_documents and
# list_open_documents may be called in different turns and return overlapping
# records with different levels of metadata completeness. The scorer keeps the
# richer record rather than silently dropping fields from the first call.
def merge_available_documents(
    current: list[dict[str, Any]] | None,
    updates: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {
        str(document.get("document_id")): {**document}
        for document in _split_list_reset(current, updates)[0]
        if document.get("document_id") is not None
    }
    for document in _split_list_reset(current, updates)[1]:
        document_id = str(document.get("document_id") or "")
        if not document_id:
            continue
        existing = merged.get(document_id)
        merged[document_id] = (
            _merge_document_pair(existing, document) if existing else {**document, "document_id": document_id}
        )

    return sorted(
        merged.values(),
        key=lambda document: (
            -int(bool(document.get("is_active"))),
            -int(bool(document.get("pinned_for_agent"))),
            -int(bool(document.get("is_open"))),
            str(document.get("document_id") or ""),
        ),
    )


def _summary_score(summary: dict[str, Any]) -> tuple[int, ...]:
    return (
        _truthy_score(summary.get("short_summary")),
        _truthy_score(summary.get("excerpt")),
        _truthy_score(summary.get("content_hash")),
        int(summary.get("version") or 0),
    )


def merge_document_summaries(
    current: dict[str, dict[str, Any]] | None,
    updates: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    merged, delta = _split_dict_reset(current, updates)
    for document_id, summary in delta.items():
        key = str(document_id)
        existing = merged.get(key)
        if existing is None or _summary_score(summary) >= _summary_score(existing):
            merged[key] = {**existing, **summary} if existing else {**summary}
        else:
            merged[key] = {**summary, **existing}
    return merged


def _span_key(span: dict[str, Any]) -> tuple[str, Any, Any, str]:
    anchor = span.get("anchor") or {}
    return (
        str(span.get("document_id") or ""),
        span.get("start_offset"),
        span.get("end_offset"),
        str(anchor.get("exactText") or ""),
    )


def _span_score(span: dict[str, Any]) -> tuple[int, ...]:
    return (
        _truthy_score(span.get("content")),
        _truthy_score(span.get("content_hash")),
        int(span.get("end_offset") or 0) - int(span.get("start_offset") or 0),
    )


def merge_read_spans(
    current: list[dict[str, Any]] | None,
    updates: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    merged: dict[tuple[str, Any, Any, str], dict[str, Any]] = {
        _span_key(span): {**span} for span in _split_list_reset(current, updates)[0]
    }
    for span in _split_list_reset(current, updates)[1]:
        key = _span_key(span)
        existing = merged.get(key)
        if existing is None or _span_score(span) >= _span_score(existing):
            merged[key] = {**existing, **span} if existing else {**span}
        else:
            merged[key] = {**span, **existing}
    return sorted(
        merged.values(),
        key=lambda span: (
            str(span.get("document_id") or ""),
            int(span.get("start_offset") or 0),
            int(span.get("end_offset") or 0),
        ),
    )


def merge_patch_history(
    current: dict[str, list[dict[str, Any]]] | None,
    updates: dict[str, list[dict[str, Any]]] | None,
) -> dict[str, list[dict[str, Any]]]:
    merged, delta = _split_dict_reset(current, updates)
    for document_id, patches in delta.items():
        deduped: dict[str, dict[str, Any]] = {}
        for patch in [*(merged.get(str(document_id), []) or []), *(patches or [])]:
            patch_id = str(patch.get("patch_id") or "")
            deduped[patch_id] = {**deduped.get(patch_id, {}), **patch} if patch_id else patch
        merged[str(document_id)] = list(deduped.values())
    return merged


def _document_read_key(document: dict[str, Any]) -> tuple[str, str]:
    return (
        str(document.get("document_id") or ""),
        str(document.get("mode") or ""),
    )


def _document_read_score(document: dict[str, Any]) -> tuple[int, ...]:
    return (
        _truthy_score(document.get("content")),
        len(str(document.get("content") or "")),
        _truthy_score(document.get("excerpt")),
        _truthy_score(document.get("short_summary")),
        _truthy_score(document.get("content_hash")),
        int(document.get("version") or 0),
    )


def merge_document_reads(
    current: list[dict[str, Any]] | None,
    updates: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str], dict[str, Any]] = {
        _document_read_key(document): {**document}
        for document in _split_list_reset(current, updates)[0]
    }
    for document in _split_list_reset(current, updates)[1]:
        key = _document_read_key(document)
        existing = merged.get(key)
        if existing is None or _document_read_score(document) >= _document_read_score(existing):
            merged[key] = {**existing, **document} if existing else {**document}
        else:
            merged[key] = {**document, **existing}
    return sorted(
        merged.values(),
        key=lambda document: (
            str(document.get("document_id") or ""),
            str(document.get("mode") or ""),
        ),
    )


def _search_result_key(result: dict[str, Any]) -> tuple[str, tuple[str, ...], int]:
    return (
        str(result.get("query") or ""),
        tuple(sorted(str(item) for item in (result.get("allowed_document_types") or []))),
        int(result.get("max_results") or 0),
    )


def merge_search_results(
    current: list[dict[str, Any]] | None,
    updates: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    merged: dict[tuple[str, tuple[str, ...], int], dict[str, Any]] = {
        _search_result_key(result): {**result} for result in _split_list_reset(current, updates)[0]
    }
    for result in _split_list_reset(current, updates)[1]:
        key = _search_result_key(result)
        existing = merged.get(key)
        if existing is None or len(result.get("matches") or []) >= len(existing.get("matches") or []):
            merged[key] = {**existing, **result} if existing else {**result}
        else:
            merged[key] = {**result, **existing}
    return list(merged.values())


class CopilotState(TypedDict):
    tenant_id: str
    user_id: str
    encounter_id: str
    active_document_id: str | None
    thread_id: str
    user_message: str
    workspace_index: dict[str, Any]
    messages: Annotated[list[AnyMessage], add_messages]
    selected_document_ids: list[str]
    retrieved_context: NotRequired[list[dict[str, Any]]]
    tool_calls: NotRequired[list[dict[str, Any]]]
    tool_results: NotRequired[Annotated[list[dict[str, Any]], _append_items]]
    planner_decisions: NotRequired[list[dict[str, Any]]]
    available_documents: NotRequired[
        Annotated[list[dict[str, Any]], merge_available_documents]
    ]
    context_view: NotRequired[dict[str, Any] | None]
    document_summaries: NotRequired[
        Annotated[dict[str, dict[str, Any]], merge_document_summaries]
    ]
    document_reads: NotRequired[Annotated[list[dict[str, Any]], merge_document_reads]]
    read_spans: NotRequired[Annotated[list[dict[str, Any]], merge_read_spans]]
    read_documents: NotRequired[list[dict[str, Any]]]
    encounter_context: NotRequired[dict[str, Any] | None]
    search_matches: NotRequired[list[dict[str, Any]]]
    search_query: NotRequired[str | None]
    search_results: NotRequired[Annotated[list[dict[str, Any]], merge_search_results]]
    patch_history: NotRequired[
        Annotated[dict[str, list[dict[str, Any]]], merge_patch_history]
    ]
    current_plan_step: NotRequired[str | None]
    iteration_count: NotRequired[int]
    max_iterations: NotRequired[int]
    max_document_reads: NotRequired[int]
    patch_operations_count: NotRequired[int]
    max_patch_operations: NotRequired[int]
    planner_retry_count: NotRequired[int]
    last_planner_error: NotRequired[str | None]
    last_tool_error: NotRequired[str | None]
    proposed_action: NotRequired[str | None]
    intent: NotRequired[str | None]
    target_document_id: NotRequired[str | None]
    target_document_title: NotRequired[str | None]
    target_selection_reason: NotRequired[str | None]
    base_version: NotRequired[int | None]
    patch_set_preview: NotRequired[dict[str, Any] | None]
    patch_preview: NotRequired[dict[str, Any] | None]
    patch_id: NotRequired[str | None]
    final_response: NotRequired[str | None]
    run_error: NotRequired[str | None]
    requires_human_review: bool
    review_result: NotRequired[Literal["approve", "reject", "edit"] | None]
    review_comment: NotRequired[str | None]
    trace_metadata: dict[str, Any]
    # Plan clínico estructurado emitido por el planner vía set_edit_plan antes de proponer patches.
    # None cuando el planner hace una edición local simple sin llamar set_edit_plan.
    # El drafter lo consume para saber qué secciones tocar y a qué nivel de impacto.
    clinical_plan: NotRequired[dict[str, Any] | None]
