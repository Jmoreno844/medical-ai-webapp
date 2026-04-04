from __future__ import annotations

import logging
from typing import Any, Sequence

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tools import BaseTool

from app.graph.state import (
    CopilotState,
    materialize_state_snapshot,
    reset_dict_state,
    reset_list_state,
)
from app.graph.tools import _build_retrieved_context, _default_selected_document_ids
from app.planner import CopilotPlanner

logger = logging.getLogger(__name__)

PATCH_REQUIRED_FIELDS = {
    "patch_id",
    "target_document_id",
    "target_document_title",
    "target_selection_reason",
    "base_version",
    "operation_type",
    "content_preview",
}


def _append_state_items(
    current: Sequence[dict[str, Any]] | None,
    updates: Sequence[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    return [*(current or []), *(updates or [])]


def _reset_transient_run_state() -> dict[str, Any]:
    # LangGraph checkpoints are thread-scoped, so a new run on the same thread
    # must clear review/proposal leftovers before the next planner turn starts.
    return {
        "available_documents": reset_list_state(),
        "context_view": None,
        "document_summaries": reset_dict_state(),
        "document_reads": reset_list_state(),
        "read_spans": reset_list_state(),
        "retrieved_context": [],
        "read_documents": [],
        "encounter_context": None,
        "search_matches": [],
        "search_query": None,
        "search_results": reset_list_state(),
        "patch_history": reset_dict_state(),
        "tool_calls": [],
        "tool_results": reset_list_state(),
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
    return all(patch_preview.get(field_name) for field_name in PATCH_REQUIRED_FIELDS)


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


def _tool_batch_size(state: CopilotState) -> int:
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
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for document in state.get("document_reads") or []:
        key = (str(document.get("document_id") or ""), str(document.get("mode") or ""))
        if not key[0] or not key[1]:
            continue
        by_key[key] = {
            "document_id": key[0],
            "title": document.get("title"),
            "type": document.get("type"),
            "mode": key[1],
            "short_summary": document.get("short_summary"),
            "excerpt": document.get("excerpt")
            or " ".join(str(document.get("content") or "").split())[:480],
            "content": document.get("content"),
            "content_hash": document.get("content_hash"),
        }

    for document_id, summary in (state.get("document_summaries") or {}).items():
        key = (str(document_id), "summary")
        by_key.setdefault(
            key,
            {
                "document_id": str(document_id),
                "title": summary.get("title"),
                "type": summary.get("type"),
                "mode": "summary",
                "short_summary": summary.get("short_summary"),
                "excerpt": summary.get("excerpt"),
                "content": None,
                "content_hash": summary.get("content_hash"),
            },
        )

    for span in state.get("read_spans") or []:
        key = (str(span.get("document_id") or ""), "span")
        candidate = {
            "document_id": str(span.get("document_id") or ""),
            "title": span.get("title"),
            "type": span.get("type"),
            "mode": "span",
            "content": span.get("content"),
            "excerpt": " ".join(str(span.get("content") or "").split())[:480],
            "content_hash": span.get("content_hash"),
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


def consolidate_tool_state(state: CopilotState) -> dict[str, Any]:
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


def _route_after_model(state: CopilotState) -> str:
    if state.get("run_error"):
        return "finalize_response"
    if state.get("requires_human_review") and _is_valid_patch_set_preview(
        state.get("patch_set_preview")
    ):
        return "interrupt_for_review"

    messages = state.get("messages") or []
    last_message = messages[-1] if messages else None
    if isinstance(last_message, AIMessage) and (last_message.tool_calls or []):
        return "tools"
    return "finalize_response"


def _route_after_tools(state: CopilotState) -> str:
    if state.get("run_error"):
        return "finalize_response"
    if state.get("requires_human_review") and _is_valid_patch_set_preview(
        state.get("patch_set_preview")
    ):
        return "interrupt_for_review"
    return "call_model"


def make_call_model_node(
    planner: CopilotPlanner,
    tools: Sequence[BaseTool | Any],
):
    def call_model(state: CopilotState) -> dict[str, Any]:
        updates: dict[str, Any] = {}

        if int(state.get("iteration_count") or 0) == 0:
            updates.update(_reset_transient_run_state())

        max_iterations = int(state.get("max_iterations") or 6)
        if int(state.get("iteration_count") or 0) >= max_iterations:
            return {
                **updates,
                **_mark_run_error(
                    "No pude completar la solicitud dentro del limite seguro de iteraciones."
                ),
            }

        current_state = materialize_state_snapshot({**state, **updates})
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

    return call_model


def interrupt_for_review(state: CopilotState) -> dict[str, Any]:
    del state
    return {}


def apply_patch(state: CopilotState) -> dict[str, Any]:
    del state
    return {}


def finalize_response(state: CopilotState) -> dict[str, Any]:
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


__all__ = [
    "apply_patch",
    "consolidate_tool_state",
    "finalize_response",
    "interrupt_for_review",
    "make_call_model_node",
    "_route_after_model",
    "_route_after_tools",
]
