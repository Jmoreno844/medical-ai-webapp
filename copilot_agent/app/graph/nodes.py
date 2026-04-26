from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Any, Sequence

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tools import BaseTool

from app.graph.state import (
    RESET_MARKER,
    CopilotState,
    materialize_state_snapshot,
    reset_dict_state,
    reset_list_state,
)
from app.graph.tools import (
    _build_retrieved_context,
    _default_selected_document_ids,
    _fallback_target_document_id_from_state,
    _has_full_read_for_document,
    draft_patch_set_from_state,
)
from app.planner import CopilotPlanner

logger = logging.getLogger(__name__)


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

NODE_PLANNER_TURN = "planner_turn"
NODE_EXECUTE_TOOLS = "execute_tools"
NODE_RECONCILE_TOOL_STATE = "reconcile_tool_state"
NODE_DRAFT_PATCH_FROM_PLAN = "draft_patch_from_plan"
NODE_WAIT_FOR_HUMAN_REVIEW = "wait_for_human_review"
NODE_APPLY_PATCH_REVIEW = "apply_patch_review"
NODE_FINALIZE_RUN = "finalize_run"

PATCH_REQUIRED_FIELDS = {
    "patch_id",
    "target_document_id",
    "target_document_title",
    "target_selection_reason",
    "base_version",
    "operation_type",
    "content_preview",
}


def _patch_field_is_present(patch_preview: dict[str, Any], field_name: str) -> bool:
    if field_name == "content_preview":
        if str(patch_preview.get("operation_type") or "") == "delete_span":
            return "content_preview" in patch_preview
        value = patch_preview.get(field_name)
        return value is not None and str(value) != ""

    value = patch_preview.get(field_name)
    return value is not None and str(value) != ""


def _append_state_items(
    current: Sequence[dict[str, Any]] | None,
    updates: Sequence[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    return [*(current or []), *(updates or [])]


def _workspace_document_map(workspace_index: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {
        str(document.get("document_id") or ""): document
        for document in ((workspace_index or {}).get("documents") or [])
        if document.get("document_id") is not None
    }


def _workspace_document_is_read_safe(document: dict[str, Any]) -> bool:
    return not (
        document.get("has_user_edits")
        or document.get("has_streaming_state")
        or document.get("has_pending_patches")
    )


def _versions_match(read_payload: dict[str, Any], workspace_document: dict[str, Any]) -> bool:
    try:
        read_version = int(read_payload.get("version"))
        workspace_version = int(workspace_document.get("version"))
    except (TypeError, ValueError):
        return False
    return read_version == workspace_version


def _is_fresh_document_artifact(
    artifact: dict[str, Any],
    *,
    workspace_documents: dict[str, dict[str, Any]],
) -> bool:
    document_id = str(artifact.get("document_id") or "")
    workspace_document = workspace_documents.get(document_id)
    if not workspace_document:
        return False
    return _workspace_document_is_read_safe(workspace_document) and _versions_match(
        artifact,
        workspace_document,
    )


def _preseed_document_reads(workspace_index: dict[str, Any] | None) -> list[dict[str, Any]]:
    pre_reads: list[dict[str, Any]] = []
    for doc in ((workspace_index or {}).get("documents") or []):
        content = doc.get("content_markdown")
        if doc.get("ai_writable") and content:
            content_hash = doc.get("content_hash") or _content_hash(str(content))
            # Deliberately do NOT pre-seed structure_mode/sections from the initial
            # workspace payload. Keeping the bootstrap symmetric across documents is
            # more important than giving richer structure to only a subset, which
            # would bias the planner toward those docs. Section extraction remains an
            # explicit backend read concern (read_document / read_document_summary).
            pre_reads.append(
                {
                    "document_id": str(doc["document_id"]),
                    "title": doc.get("title"),
                    "type": doc.get("type"),
                    "version": doc.get("version"),
                    "mode": "full",
                    "content": content,
                    "content_hash": content_hash,
                }
            )
    return pre_reads


def _read_document_view(read_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "document_id": str(read_payload.get("document_id") or ""),
        "title": read_payload.get("title"),
        "type": read_payload.get("type"),
        "version": read_payload.get("version"),
        "mode": read_payload.get("mode"),
        "content": read_payload.get("content"),
        "content_hash": read_payload.get("content_hash"),
        "structure_mode": read_payload.get("structure_mode"),
        "sections": list(read_payload.get("sections") or []),
    }


def _carry_fresh_reads(
    *,
    state: CopilotState,
    workspace_documents: dict[str, dict[str, Any]],
    pre_reads: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    pre_read_keys = {
        (str(read.get("document_id") or ""), str(read.get("mode") or ""))
        for read in pre_reads
    }
    carried_reads = [
        read
        for read in (state.get("document_reads") or [])
        if _is_fresh_document_artifact(read, workspace_documents=workspace_documents)
        and (str(read.get("document_id") or ""), str(read.get("mode") or ""))
        not in pre_read_keys
    ]
    carried_summaries = {
        str(document_id): summary
        for document_id, summary in (state.get("document_summaries") or {}).items()
        if _is_fresh_document_artifact(
            {"document_id": str(document_id), **summary},
            workspace_documents=workspace_documents,
        )
    }
    carried_spans = [
        span
        for span in (state.get("read_spans") or [])
        if _is_fresh_document_artifact(span, workspace_documents=workspace_documents)
    ]
    return carried_reads, carried_summaries, carried_spans


def _short_memory_text(value: Any, *, max_length: int = 240) -> str:
    return " ".join(str(value or "").split())[:max_length]


def _append_memory_note(
    notes: list[dict[str, Any]],
    *,
    source: str,
    message: Any,
) -> None:
    text = _short_memory_text(message)
    if not text:
        return
    candidate = {"source": source, "message": text}
    if candidate not in notes:
        notes.append(candidate)


def _next_run_memory_notes(state: CopilotState) -> list[dict[str, Any]]:
    notes = [
        note
        for note in (state.get("run_memory_notes") or [])
        if isinstance(note, dict) and note.get("message")
    ][-5:]

    for field_name in ("last_tool_error", "last_planner_error", "run_error"):
        if state.get(field_name):
            _append_memory_note(
                notes,
                source=field_name,
                message=state.get(field_name),
            )

    for result in (state.get("tool_results") or [])[-8:]:
        payload = result.get("payload") or {}
        if payload.get("error"):
            _append_memory_note(
                notes,
                source=str(result.get("tool_name") or "tool_error"),
                message=payload.get("error"),
            )

    patch_set_preview = state.get("patch_set_preview") or {}
    for patch in (patch_set_preview.get("patches") or [])[-5:]:
        if patch.get("conflict_reason"):
            _append_memory_note(
                notes,
                source="patch_conflict",
                message=patch.get("conflict_reason"),
            )

    if state.get("review_result") in {"reject", "edit"} and state.get("review_comment"):
        _append_memory_note(
            notes,
            source=f"review_{state.get('review_result')}",
            message=state.get("review_comment"),
        )

    return notes[-5:]


def _reset_transient_run_state(
    *,
    state: CopilotState,
    workspace_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # LangGraph checkpoints are thread-scoped, so a new run on the same thread
    # inherits the full prior checkpoint (tool reads, proposals, counters).
    # This function clears per-run control state while preserving read artifacts
    # that are still fresh against the current workspace version/flags.
    # Called only when iteration_count == 0 (first call_model invocation per run).

    # Pre-seed writable documents from the workspace_index content sent by the
    # frontend. Docs with ai_writable=True carry their full markdown so the agent
    # can call propose_* on turn 1 without needing a read_document round-trip.
    workspace_documents = _workspace_document_map(workspace_index)
    pre_reads = _preseed_document_reads(workspace_index)
    carried_reads, carried_summaries, carried_spans = _carry_fresh_reads(
        state=state,
        workspace_documents=workspace_documents,
        pre_reads=pre_reads,
    )

    doc_reads_update: list[dict[str, Any]] = [
        {RESET_MARKER: True},
        *carried_reads,
        *pre_reads,
    ]
    document_summaries_update = {
        RESET_MARKER: True,
        **carried_summaries,
    }
    read_spans_update = [
        {RESET_MARKER: True},
        *carried_spans,
    ]

    # Derive the read_documents view up-front so the planner context already
    # shows these documents as read on turn 1, before reconcile_tool_state runs.
    pre_read_documents: list[dict[str, Any]] = [
        _read_document_view(read)
        for read in [*carried_reads, *pre_reads]
    ]

    return {
        "available_documents": reset_list_state(),
        "context_view": None,
        "document_summaries": document_summaries_update,
        "document_reads": doc_reads_update,
        "read_spans": read_spans_update,
        "retrieved_context": [],
        "read_documents": pre_read_documents,
        "encounter_context": None,
        "search_matches": [],
        "search_query": None,
        "search_results": reset_list_state(),
        "patch_history": reset_dict_state(),
        "tool_calls": [],
        "tool_results": reset_list_state(),
        "run_memory_notes": _next_run_memory_notes(state),
        "planner_decisions": [],
        "current_plan_step": "start",
        "iteration_count": 0,
        "patch_operations_count": 0,
        "proposed_action": None,
        "patch_set_preview": None,
        "patch_preview": None,
        "patch_id": None,
        "final_response": None,
        "run_error": None,
        "requires_human_review": False,
        "review_result": None,
        "review_comment": None,
        "target_document_id": None,
        "target_document_title": None,
        "target_selection_reason": None,
        "base_version": None,
        "last_planner_error": None,
        "last_tool_error": None,
        # clinical_plan se resetea con cada run para que un plan de propagación
        # no contamine el siguiente turno del planner.
        "clinical_plan": None,
        "next_required_action": None,
        "planned_target_document_id": None,
        "patch_validation_retry_used": False,
    }


def _mark_run_error(message: str) -> dict[str, Any]:
    return {
        "run_error": message,
        "final_response": None,
        "requires_human_review": False,
    }


def _is_valid_patch_preview(patch_preview: dict[str, Any] | None) -> bool:
    if not isinstance(patch_preview, dict):
        return False
    return all(_patch_field_is_present(patch_preview, field_name) for field_name in PATCH_REQUIRED_FIELDS)


def _is_valid_patch_set_preview(patch_set_preview: dict[str, Any] | None) -> bool:
    if not isinstance(patch_set_preview, dict):
        return False
    required_fields = {
        "patch_set_id",
        "target_document_id",
        "target_document_title",
        "target_selection_reason",
        "base_version",
        "patches",
    }
    if not all(patch_set_preview.get(field_name) for field_name in required_fields):
        return False
    patches = patch_set_preview.get("patches")
    return isinstance(patches, list) and patches and all(
        _is_valid_patch_preview(patch) for patch in patches
    )


def _message_text(message: BaseMessage | None) -> str:
    if message is None:
        return ""
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text_value = item.get("text")
                if text_value:
                    parts.append(str(text_value))
        return "\n".join(part.strip() for part in parts if part).strip()
    return str(content).strip()


def _planner_decision_from_message(
    message: AIMessage,
    *,
    intent: str | None,
) -> dict[str, Any]:
    tool_calls = []
    for tool_call in message.tool_calls or []:
        tool_calls.append(
            {
                "id": str(tool_call.get("id") or ""),
                "name": str(tool_call.get("name") or ""),
                "args": tool_call.get("args") or {},
            }
        )

    if tool_calls:
        first_call = tool_calls[0]
        return {
            "action_type": "call_tool",
            "tool_name": first_call["name"],
            "tool_input": first_call["args"],
            "reasoning_summary": _message_text(message) or "tool_call_requested",
            "response_content": None,
            "intent": intent,
            "target_document_hint": (first_call["args"] or {}).get("target_document_id"),
            "tool_calls": tool_calls,
        }

    return {
        "action_type": "respond",
        "tool_name": None,
        "tool_input": {},
        "reasoning_summary": "direct_response",
        "response_content": _message_text(message) or None,
        "intent": intent,
        "target_document_hint": None,
        "tool_calls": [],
    }


def _tool_call_summaries(message: AIMessage) -> list[dict[str, Any]]:
    reasoning_summary = _message_text(message) or "tool_call_requested"
    return [
        {
            "tool_name": str(tool_call.get("name") or ""),
            "tool_input": tool_call.get("args") or {},
            "reasoning_summary": reasoning_summary,
        }
        for tool_call in message.tool_calls or []
    ]


def _current_messages(state: CopilotState) -> Sequence[BaseMessage]:
    return tuple(state.get("messages") or [])


def _pending_plan_full_read_message(state: CopilotState) -> AIMessage | None:
    if state.get("next_required_action") != "draft_patch_set":
        return None

    clinical_plan = state.get("clinical_plan") or {}
    if not clinical_plan.get("needs_full_note"):
        return None

    target_document_id = str(
        state.get("planned_target_document_id")
        or _fallback_target_document_id_from_state(state)
        or ""
    ).strip()
    if not target_document_id or _has_full_read_for_document(
        state,
        document_id=target_document_id,
    ):
        return None

    return AIMessage(
        content="Leeré la nota completa requerida por el plan clínico antes de redactar los patches.",
        tool_calls=[
            {
                "name": "read_document",
                "args": {
                    "document_id": target_document_id,
                    "mode": "full",
                },
                "id": f"runtime-read-full-{uuid.uuid4()}",
                "type": "tool_call",
            }
        ],
    )


def _pending_plan_ready_to_draft(state: CopilotState) -> bool:
    if state.get("next_required_action") != "draft_patch_set":
        return False
    target_document_id = str(
        state.get("planned_target_document_id")
        or _fallback_target_document_id_from_state(state)
        or ""
    ).strip()
    if not target_document_id:
        return False
    clinical_plan = state.get("clinical_plan") or {}
    return (
        not clinical_plan.get("needs_full_note")
        or _has_full_read_for_document(state, document_id=target_document_id)
    )


def _tool_batch_size(state: CopilotState) -> int:
    # LangGraph delivers all results from a parallel tool batch as a single state
    # update. Counting the tool_calls on the latest AIMessage tells us exactly
    # how many tool_results belong to the current batch vs. prior turns.
    messages = state.get("messages") or []
    for message in reversed(messages):
        if isinstance(message, AIMessage) and (message.tool_calls or []):
            return len(message.tool_calls or [])
    return 0


def _current_batch_tool_results(state: CopilotState) -> list[dict[str, Any]]:
    batch_size = _tool_batch_size(state)
    if batch_size <= 0:
        return []
    return list((state.get("tool_results") or [])[-batch_size:])


def _derive_last_tool_error(state: CopilotState) -> str | None:
    errors: list[str] = []
    for result in _current_batch_tool_results(state):
        payload = result.get("payload") or {}
        error = str(payload.get("error") or "").strip()
        if error:
            errors.append(error)

    if not errors:
        return None
    return " | ".join(dict.fromkeys(errors))


def _derive_read_documents(state: CopilotState) -> list[dict[str, Any]]:
    # Consolidates three state buckets (document_reads, document_summaries,
    # read_spans) into one normalized list keyed by (document_id, mode).
    # Each bucket may hold the same document at different granularities.
    # This unified view is what the planner context and the patch drafter receive.
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for document in state.get("document_reads") or []:
        key = (str(document.get("document_id") or ""), str(document.get("mode") or ""))
        if not key[0] or not key[1]:
            continue
        by_key[key] = {
            "document_id": key[0],
            "title": document.get("title"),
            "type": document.get("type"),
            "version": document.get("version"),
            "mode": key[1],
            "content": document.get("content"),
            "content_hash": document.get("content_hash"),
            "structure_mode": document.get("structure_mode"),
            "sections": list(document.get("sections") or []),
        }

    for document_id, summary in (state.get("document_summaries") or {}).items():
        key = (str(document_id), "summary")
        by_key.setdefault(
            key,
            {
                "document_id": str(document_id),
                "title": summary.get("title"),
                "type": summary.get("type"),
                "version": summary.get("version"),
                "mode": "summary",
                "content": None,
                "content_hash": summary.get("content_hash"),
                "structure_mode": summary.get("structure_mode"),
                "sections": list(summary.get("sections") or []),
            },
        )

    for span in state.get("read_spans") or []:
        key = (str(span.get("document_id") or ""), "span")
        candidate = {
            "document_id": str(span.get("document_id") or ""),
            "title": span.get("title"),
            "type": span.get("type"),
            "version": span.get("version"),
            "mode": "span",
            "content": span.get("content"),
            "content_hash": span.get("content_hash"),
            "structure_mode": span.get("structure_mode"),
            "sections": list(span.get("sections") or []),
        }
        existing = by_key.get(key)
        if existing is None or len(str(candidate.get("content") or "")) >= len(
            str(existing.get("content") or "")
        ):
            by_key[key] = candidate

    return list(by_key.values())


def _derive_selected_document_ids(state: CopilotState) -> list[str]:
    if state.get("available_documents"):
        return _default_selected_document_ids(state)
    return [str(document_id) for document_id in state.get("selected_document_ids", [])]


def _derive_search_legacy_fields(state: CopilotState) -> tuple[str | None, list[dict[str, Any]]]:
    search_results = state.get("search_results") or []
    if len(search_results) != 1:
        return None, []
    only_result = search_results[0]
    return only_result.get("query"), list(only_result.get("matches") or [])


def reconcile_tool_state(state: CopilotState) -> dict[str, Any]:
    # Dedicated reconciliation node between the tools node and call_model.
    # When the planner emits parallel tool calls each ToolNode write lands in state
    # independently. Without this node the next call_model turn would see a
    # partially written snapshot. Running consolidation here gives the planner a
    # single stable, de-duplicated view of all reads before the next decision.
    read_documents = _derive_read_documents(state)
    search_query, search_matches = _derive_search_legacy_fields(state)
    return {
        "read_documents": read_documents,
        "retrieved_context": _build_retrieved_context(
            context_view=state.get("context_view"),
            read_documents=read_documents,
            read_spans=state.get("read_spans") or [],
        ),
        "selected_document_ids": _derive_selected_document_ids(state),
        "last_tool_error": _derive_last_tool_error(state),
        "search_query": search_query,
        "search_matches": search_matches,
        # Recompute after selection/read consolidation so later planner turns always
        # see a stable post-batch snapshot instead of partial concurrent tool writes.
        "current_plan_step": state.get("current_plan_step"),
    }


def route_after_planner_turn(state: CopilotState) -> str:
    if state.get("run_error"):
        return NODE_FINALIZE_RUN
    if state.get("requires_human_review") and _is_valid_patch_set_preview(
        state.get("patch_set_preview")
    ):
        return NODE_WAIT_FOR_HUMAN_REVIEW
    if _pending_plan_ready_to_draft(state):
        return NODE_DRAFT_PATCH_FROM_PLAN

    messages = state.get("messages") or []
    last_message = messages[-1] if messages else None
    if isinstance(last_message, AIMessage) and (last_message.tool_calls or []):
        return NODE_EXECUTE_TOOLS
    return NODE_FINALIZE_RUN


def route_after_tool_execution(state: CopilotState) -> str:
    if state.get("run_error"):
        return NODE_FINALIZE_RUN
    if state.get("requires_human_review") and _is_valid_patch_set_preview(
        state.get("patch_set_preview")
    ):
        return NODE_WAIT_FOR_HUMAN_REVIEW
    if state.get("next_required_action") == "draft_patch_set":
        target_document_id = str(
            state.get("planned_target_document_id")
            or _fallback_target_document_id_from_state(state)
            or ""
        ).strip()
        clinical_plan = state.get("clinical_plan") or {}
        if (
            target_document_id
            and (
                not clinical_plan.get("needs_full_note")
                or _has_full_read_for_document(state, document_id=target_document_id)
            )
        ):
            return NODE_DRAFT_PATCH_FROM_PLAN
    return NODE_PLANNER_TURN


def make_draft_patch_from_plan_node(
    planner: CopilotPlanner,
):
    def draft_patch_from_plan(state: CopilotState) -> dict[str, Any]:
        target_document_id = str(
            state.get("planned_target_document_id")
            or _fallback_target_document_id_from_state(state)
            or ""
        ).strip()
        if not target_document_id:
            return {
                "last_tool_error": (
                    "Existe un edit_plan pendiente pero el runtime no pudo resolver "
                    "el documento target para redactar los patches."
                ),
                "next_required_action": None,
                "planned_target_document_id": None,
            }

        result = draft_patch_set_from_state(
            planner=planner,
            state=state,
            tool_name="propose_replace_span",
            target_document_id=target_document_id,
        )
        if result["ok"]:
            return result["updates"]
        return result.get("updates") or {
            "last_tool_error": result["error_message"],
            "next_required_action": None,
            "planned_target_document_id": None,
        }

    return draft_patch_from_plan


def make_planner_turn_node(
    planner: CopilotPlanner,
    tools: Sequence[BaseTool | Any],
):
    def planner_turn(state: CopilotState) -> dict[str, Any]:
        updates: dict[str, Any] = {}

        if int(state.get("iteration_count") or 0) == 0:
            updates.update(_reset_transient_run_state(
                state=state,
                workspace_index=state.get("workspace_index"),
            ))

        max_iterations = int(state.get("max_iterations") or 6)
        if int(state.get("iteration_count") or 0) >= max_iterations:
            return {
                **updates,
                **_mark_run_error(
                    "No pude completar la solicitud dentro del limite seguro de iteraciones."
                ),
            }

        current_state = materialize_state_snapshot({**state, **updates})
        ai_message = _pending_plan_full_read_message(current_state)
        if ai_message is None and _pending_plan_ready_to_draft(current_state):
            return {
                **updates,
                "current_plan_step": "draft_patch_set",
                "proposed_action": "draft_patch_set",
                "iteration_count": int(state.get("iteration_count") or 0) + 1,
            }
        if ai_message is None:
            try:
                ai_message = planner.invoke_model(
                    state=current_state,
                    messages=_current_messages(current_state),
                    tools=tools,
                )
            except Exception as error:
                logger.exception("Falla real al invocar planner con tools paralelas")
                last_tool_error = str(current_state.get("last_tool_error") or "").strip()
                return {
                    **updates,
                    "last_planner_error": str(error),
                    **_mark_run_error(
                        last_tool_error
                        or "El planner del copiloto fallo al decidir el siguiente paso."
                    ),
                }

        planner_decision = _planner_decision_from_message(ai_message, intent=state.get("intent"))
        new_iteration_count = int(state.get("iteration_count") or 0) + 1
        tool_calls = _tool_call_summaries(ai_message)
        response_text = _message_text(ai_message)

        updates.update(
            {
                "messages": [ai_message],
                "planner_decisions": _append_state_items(
                    current_state.get("planner_decisions"),
                    [planner_decision],
                ),
                "tool_calls": _append_state_items(
                    current_state.get("tool_calls"),
                    tool_calls,
                ),
                "current_plan_step": planner_decision["action_type"],
                "proposed_action": planner_decision["action_type"],
                "iteration_count": new_iteration_count,
                "last_planner_error": None,
            }
        )

        if tool_calls:
            return updates

        if current_state.get("next_required_action") == "draft_patch_set":
            return {
                **updates,
                **_mark_run_error(
                    "Existe un edit_plan pendiente, pero el planner no avanzo con lectura ni drafting."
                ),
            }

        if not response_text:
            return {
                **updates,
                **_mark_run_error(
                    "El planner no devolvio respuesta util ni tool calls para este turno."
                ),
            }

        updates["final_response"] = response_text
        updates["requires_human_review"] = False
        # Edit flows may legitimately pause for clarification when the model still
        # lacks data to draft a safe patch. We only require waiting_review once a
        # real patch_set_preview exists; otherwise a conversational clarification is
        # treated as a clean completed turn instead of a synthetic runtime failure.
        return updates

    return planner_turn


def wait_for_human_review(state: CopilotState) -> dict[str, Any]:
    # No-op node. LangGraph pauses graph execution here when review_result is None.
    # The run is stored as waiting_review; the frontend resumes it via /resume.
    del state
    return {}


def apply_patch_review(state: CopilotState) -> dict[str, Any]:
    # Intentional stub. Django owns the actual clinical write and audit trail.
    # This node exists to keep the graph edge explicit and auditable in traces.
    # If the copilot ever gets direct write authority, this is the right place.
    del state
    return {}


def finalize_run(state: CopilotState) -> dict[str, Any]:
    if state.get("requires_human_review") and _is_valid_patch_set_preview(
        state.get("patch_set_preview")
    ):
        return {}

    if state.get("run_error"):
        return {
            "requires_human_review": False,
        }

    if state.get("final_response"):
        return {}

    return {
        "final_response": "No pude completar la solicitud del copiloto dentro de los limites de este run.",
        "requires_human_review": False,
    }


consolidate_tool_state = reconcile_tool_state
_route_after_model = route_after_planner_turn
_route_after_tools = route_after_tool_execution
make_call_model_node = make_planner_turn_node
interrupt_for_review = wait_for_human_review
apply_patch = apply_patch_review
finalize_response = finalize_run


__all__ = [
    "NODE_APPLY_PATCH_REVIEW",
    "NODE_DRAFT_PATCH_FROM_PLAN",
    "NODE_EXECUTE_TOOLS",
    "NODE_FINALIZE_RUN",
    "NODE_PLANNER_TURN",
    "NODE_RECONCILE_TOOL_STATE",
    "NODE_WAIT_FOR_HUMAN_REVIEW",
    "apply_patch",
    "apply_patch_review",
    "consolidate_tool_state",
    "finalize_response",
    "finalize_run",
    "interrupt_for_review",
    "make_draft_patch_from_plan_node",
    "make_call_model_node",
    "make_planner_turn_node",
    "reconcile_tool_state",
    "route_after_planner_turn",
    "route_after_tool_execution",
    "wait_for_human_review",
    "_route_after_model",
    "_route_after_tools",
]
