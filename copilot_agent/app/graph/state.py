from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import Annotated


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
    tool_results: NotRequired[list[dict[str, Any]]]
    planner_decisions: NotRequired[list[dict[str, Any]]]
    available_documents: NotRequired[list[dict[str, Any]]]
    context_view: NotRequired[dict[str, Any] | None]
    document_summaries: NotRequired[dict[str, dict[str, Any]]]
    read_spans: NotRequired[list[dict[str, Any]]]
    read_documents: NotRequired[list[dict[str, Any]]]
    encounter_context: NotRequired[dict[str, Any] | None]
    search_matches: NotRequired[list[dict[str, Any]]]
    search_query: NotRequired[str | None]
    patch_history: NotRequired[dict[str, list[dict[str, Any]]]]
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
