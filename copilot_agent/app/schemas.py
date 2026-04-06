from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class WorkspaceDocumentSummary(BaseModel):
    document_id: str
    type: str
    title: str
    status: str
    source: str
    ai_readable: bool
    ai_writable: bool
    version: int
    updated_at: str
    is_active: bool
    is_open: bool
    has_dirty_draft: bool
    has_streaming_state: bool
    hidden_from_agent: bool
    pinned_for_agent: bool
    excerpt: str | None = None
    short_summary: str | None = None
    estimated_tokens: int | None = None
    has_pending_patches: bool = False
    # Full markdown pre-loaded by the frontend for writable docs.
    # Used in _build_initial_state to seed document_reads so the agent can
    # propose patches without a read_document round-trip.
    content_markdown: str | None = None


class WorkspaceIndexPayload(BaseModel):
    encounter_id: str
    workspace_version: str
    active_document_id: str | None = None
    open_document_ids: list[str] = Field(default_factory=list)
    documents: list[WorkspaceDocumentSummary] = Field(default_factory=list)


class RunCreateRequest(BaseModel):
    tenant_id: str
    user_id: str
    encounter_id: str
    thread_id: str
    active_document_id: str | None = None
    user_message: str
    workspace_index: WorkspaceIndexPayload
    selected_document_ids: list[str] = Field(default_factory=list)
    trace_metadata: dict[str, Any] = Field(default_factory=dict)


class RunResumeRequest(BaseModel):
    patch_set_id: str
    review_result: Literal["approve", "reject", "edit"]
    reviewer_id: str
    comment: str | None = None
    trace_metadata: dict[str, Any] = Field(default_factory=dict)


class PatchSetPatchPreview(BaseModel):
    patch_id: str
    patch_type: str
    order_index: int
    anchor: dict[str, Any] = Field(default_factory=dict)
    expected_hash: str | None = None
    old_text: str | None = None
    new_text: str | None = None
    resolved_start: int | None = None
    resolved_end: int | None = None
    confidence: float | None = None
    conflict_reason: str | None = None
    status: str = "pending"
    before_preview: str | None = None
    after_preview: str | None = None
    document_preview_after: str | None = None
    rationale: str | None = None
    content_preview: str


class PatchSetPreview(BaseModel):
    patch_set_id: str
    target_document_id: str
    target_document_title: str | None = None
    target_selection_reason: str | None = None
    base_version: int
    base_hash: str
    rationale: str | None = None
    source_context_document_ids: list[str] = Field(default_factory=list)
    document_preview_after: str | None = None
    patches: list[PatchSetPatchPreview] = Field(default_factory=list)


class RunEvent(BaseModel):
    sequence: int | None = None
    event: str
    run_id: str
    thread_id: str
    created_at: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class RunStatusResponse(BaseModel):
    run_id: str
    thread_id: str
    status: str
    intent: str | None = None
    requires_human_review: bool = False
    active_patch_set_id: str | None = None
    patch_set_preview: PatchSetPreview | None = None
    final_response: str | None = None
    applied_patch_set_id: str | None = None
    applied_document_id: str | None = None
    applied_content: str | None = None
    applied_version: int | None = None
    trace_metadata: dict[str, Any] = Field(default_factory=dict)


class RunEventsResponse(BaseModel):
    events: list[RunEvent] = Field(default_factory=list)
    status: str
    next_after_sequence: int = 0
    done: bool
