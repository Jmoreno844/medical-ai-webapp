from typing import Any, Literal, NotRequired, TypedDict


class CopilotState(TypedDict):
    tenant_id: str
    user_id: str
    encounter_id: str
    active_document_id: str | None
    thread_id: str
    user_message: str
    intent: NotRequired[str | None]
    workspace_index: dict[str, Any]
    messages: NotRequired[list[dict[str, Any]]]
    selected_document_ids: list[str]
    available_documents: NotRequired[list[dict[str, Any]]]
    context_view: NotRequired[dict[str, Any] | None]
    document_summaries: NotRequired[dict[str, dict[str, Any]]]
    read_spans: NotRequired[list[dict[str, Any]]]
    retrieved_context: list[dict[str, Any]]
    read_documents: NotRequired[list[dict[str, Any]]]
    encounter_context: NotRequired[dict[str, Any] | None]
    search_matches: NotRequired[list[dict[str, Any]]]
    search_query: NotRequired[str | None]
    patch_history: NotRequired[dict[str, list[dict[str, Any]]]]
    tool_calls: NotRequired[list[dict[str, Any]]]
    tool_results: NotRequired[list[dict[str, Any]]]
    planner_decisions: NotRequired[list[dict[str, Any]]]
    current_plan_step: NotRequired[str | None]
    pending_action: NotRequired[dict[str, Any] | None]
    pending_tool_result: NotRequired[dict[str, Any] | None]
    iteration_count: NotRequired[int]
    max_iterations: NotRequired[int]
    max_document_reads: NotRequired[int]
    patch_operations_count: NotRequired[int]
    max_patch_operations: NotRequired[int]
    proposed_action: NotRequired[str | None]
    target_document_id: NotRequired[str | None]
    target_document_title: NotRequired[str | None]
    target_selection_reason: NotRequired[str | None]
    base_version: NotRequired[int | None]
    patch_preview: NotRequired[dict[str, Any] | None]
    patch_id: NotRequired[str | None]
    final_response: NotRequired[str | None]
    run_error: NotRequired[str | None]
    requires_human_review: bool
    review_result: NotRequired[Literal["approve", "reject", "edit"] | None]
    review_comment: NotRequired[str | None]
    trace_metadata: dict[str, Any]
