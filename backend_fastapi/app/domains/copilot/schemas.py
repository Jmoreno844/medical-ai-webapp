from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

CopilotPatchOperationType = Literal[
    "replace_span",
    "insert_before",
    "insert_after",
    "insert_after_span",
    "delete_span",
    "rewrite_document",
]
CopilotNormalizedPatchOperationType = Literal[
    "replace_span",
    "insert_before",
    "insert_after",
    "delete_span",
]


class CopilotPatchAnchor(BaseModel):
    exactText: str | None = None
    prefixText: str | None = None
    suffixText: str | None = None
    startOffset: int | None = None
    endOffset: int | None = None


class WorkspaceDocumentSummaryIn(BaseModel):
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
    has_user_edits: bool = False
    has_streaming_state: bool
    hidden_from_agent: bool = False
    pinned_for_agent: bool = False
    estimated_tokens: int | None = None
    has_pending_patches: bool = False
    content_markdown: str | None = None
    content_json: dict[str, Any] | None = None


class WorkspaceIndexIn(BaseModel):
    encounter_id: str
    workspace_version: str
    active_document_id: str | None = None
    open_document_ids: list[str] = Field(default_factory=list)
    documents: list[WorkspaceDocumentSummaryIn] = Field(default_factory=list)


class CopilotSessionIn(BaseModel):
    encounter_id: int


class CopilotSessionOut(BaseModel):
    thread_id: str
    capability: Literal["read_only"]


class CopilotMessageIn(BaseModel):
    encounter_id: int
    thread_id: str
    user_message: str
    workspace_index: WorkspaceIndexIn
    active_document_id: str | None = None
    selected_document_ids: list[str] = Field(default_factory=list)


class CopilotRunOut(BaseModel):
    run_id: str
    thread_id: str
    status: str
    intent: str | None = None
    requires_human_review: bool = False
    active_patch_set_id: str | None = None
    final_response: str | None = None
    applied_patch_set_id: str | None = None
    applied_patch_id: str | None = None
    applied_document_id: str | None = None
    applied_content: str | None = None
    applied_version: int | None = None
    trace_metadata: dict[str, Any] = Field(default_factory=dict)


class CopilotPatchOut(BaseModel):
    patch_id: str
    patch_set_id: str | None = None
    run_id: str
    target_document_id: str
    base_version: int
    order_index: int = 0
    patch_type: CopilotPatchOperationType
    operation_type: CopilotPatchOperationType
    normalized_operation_type: CopilotNormalizedPatchOperationType
    anchor: CopilotPatchAnchor = Field(default_factory=CopilotPatchAnchor)
    expected_hash: str | None = None
    replacement_text: str | None = None
    inserted_text: str | None = None
    old_text: str | None = None
    new_text: str | None = None
    resolved_start: int | None = None
    resolved_end: int | None = None
    confidence: float | None = None
    conflict_reason: str | None = None
    document_preview_after: str | None = None
    content_preview: str
    rationale: str | None = None
    source_context_document_ids: list[str] = Field(default_factory=list)
    target_document_title: str | None = None
    target_selection_reason: str | None = None
    status: Literal["pending", "accepted", "rejected", "conflicted", "applied", "stale"]
    review_comment: str | None = None
    section: str | None = None
    created_at: datetime
    updated_at: datetime


class CopilotPatchSetOut(BaseModel):
    patch_set_id: str
    run_id: str
    target_document_id: str
    base_version: int
    base_hash: str
    rationale: str | None = None
    source_context_document_ids: list[str] = Field(default_factory=list)
    target_document_title: str | None = None
    target_selection_reason: str | None = None
    document_preview_after: str | None = None
    status: Literal["pending", "partially_accepted", "accepted", "rejected", "stale", "applied"]
    review_comment: str | None = None
    patches: list[CopilotPatchOut] = Field(default_factory=list)
    edit_scope: str | None = None
    clinical_impact_level: str | None = None
    affected_sections: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class CopilotReviewIn(BaseModel):
    patch_id: str
    decision: Literal["approve", "reject"]
    comment: str | None = None
    document_version: int | None = None


class CopilotPatchDecisionIn(BaseModel):
    patch_id: str
    comment: str | None = None


class CopilotPatchSetDecisionIn(BaseModel):
    comment: str | None = None
    document_version: int | None = None


class CopilotInternalToolRequest(BaseModel):
    run_id: str
    thread_id: str
    encounter_id: int
    user_id: int


class CopilotListOpenDocumentsIn(CopilotInternalToolRequest):
    workspace_index: WorkspaceIndexIn


class CopilotToolDocumentOut(BaseModel):
    document_id: str
    title: str
    type: str
    status: str
    source: str
    ai_writable: bool = False
    version: int
    updated_at: str
    is_active: bool = False
    is_open: bool = False
    pinned_for_agent: bool = False


class CopilotListOpenDocumentsOut(BaseModel):
    documents: list[CopilotToolDocumentOut] = Field(default_factory=list)


class CopilotReadDocumentIn(CopilotInternalToolRequest):
    document_id: int
    mode: Literal["full"] = "full"


class CopilotDocumentSectionOut(BaseModel):
    section_id: str
    label: str
    heading: str
    normalized_heading: str
    heading_level: int | None = None
    heading_style: str
    resolution_source: str
    start_offset: int
    content_start_offset: int
    end_offset: int
    content_preview: str = ""


class CopilotReadDocumentOut(BaseModel):
    document_id: str
    encounter_id: str
    title: str
    type: str
    version: int
    content_hash: str
    updated_at: str
    mode: Literal["full"]
    content: str | None = None
    structure_mode: Literal["structured", "unstructured"] = "unstructured"
    sections: list[CopilotDocumentSectionOut] = Field(default_factory=list)


class CopilotSearchDocumentsIn(CopilotInternalToolRequest):
    query: str
    max_results: int = Field(default=3, ge=1, le=10)
    allowed_document_types: list[str] = Field(default_factory=list)


class CopilotSearchDocumentMatchOut(BaseModel):
    document_id: str
    title: str
    type: str
    updated_at: str
    snippet: str
    score: float
    anchor: dict[str, Any] = Field(default_factory=dict)


class CopilotSearchDocumentsOut(BaseModel):
    query: str
    matches: list[CopilotSearchDocumentMatchOut] = Field(default_factory=list)


class CopilotListEncounterDocumentsIn(CopilotInternalToolRequest):
    pass


class CopilotListEncounterDocumentsOut(BaseModel):
    documents: list[CopilotToolDocumentOut] = Field(default_factory=list)


class CopilotReadDocumentSummaryIn(CopilotInternalToolRequest):
    document_id: int


class CopilotReadDocumentSummaryOut(BaseModel):
    document_id: str
    encounter_id: str
    title: str
    type: str
    version: int
    content_hash: str
    updated_at: str
    structure_mode: Literal["structured", "unstructured"] = "unstructured"
    sections: list[CopilotDocumentSectionOut] = Field(default_factory=list)


class CopilotReadDocumentSpanIn(CopilotInternalToolRequest):
    document_id: int
    exact_text: str | None = None
    prefix_text: str | None = None
    suffix_text: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    max_chars: int = Field(default=600, ge=1, le=20000)


class CopilotReadDocumentSpanOut(BaseModel):
    document_id: str
    title: str
    type: str
    version: int
    content_hash: str
    content: str
    start_offset: int
    end_offset: int
    anchor: dict[str, Any] = Field(default_factory=dict)


class CopilotReadPatchHistoryIn(CopilotInternalToolRequest):
    document_id: int
    limit: int = Field(default=5, ge=1, le=20)


class CopilotPatchHistoryItemOut(BaseModel):
    patch_id: str
    operation_type: str
    status: str
    rationale: str | None = None
    created_at: datetime


class CopilotReadPatchHistoryOut(BaseModel):
    document_id: str
    patches: list[CopilotPatchHistoryItemOut] = Field(default_factory=list)


class CopilotReadEncounterContextIn(CopilotInternalToolRequest):
    pass


class CopilotEncounterContextOut(BaseModel):
    encounter_id: str
    encounter_name: str | None = None
    occurred_at: str | None = None
    has_been_transcribed: bool = False
    patient_id: str | None = None
    patient_summary: str | None = None
