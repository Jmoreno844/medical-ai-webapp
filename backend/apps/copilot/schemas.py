from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from ninja import Schema
from pydantic import Field


class WorkspaceDocumentSummaryIn(Schema):
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
    excerpt: Optional[str] = None
    short_summary: Optional[str] = None
    estimated_tokens: Optional[int] = None
    has_pending_patches: bool = False
    # Full markdown content for ai_writable docs pre-loaded by the frontend.
    # Django passes this through to the agent verbatim; it never persists it.
    content_markdown: Optional[str] = None
    # Rich editor JSON pre-loaded by the frontend for future structured review
    # flows. The current agent still operates on markdown.
    content_json: Optional[dict[str, Any]] = None


class WorkspaceIndexIn(Schema):
    encounter_id: str
    workspace_version: str
    active_document_id: Optional[str] = None
    open_document_ids: list[str] = Field(default_factory=list)
    documents: list[WorkspaceDocumentSummaryIn] = Field(default_factory=list)


class CopilotSessionIn(Schema):
    encounter_id: int


class CopilotSessionOut(Schema):
    thread_id: str
    capability: Literal["read_only"]


class CopilotMessageIn(Schema):
    encounter_id: int
    thread_id: str
    user_message: str
    workspace_index: WorkspaceIndexIn
    active_document_id: Optional[str] = None
    selected_document_ids: list[str] = Field(default_factory=list)


class CopilotRunOut(Schema):
    run_id: str
    thread_id: str
    status: str
    intent: Optional[str] = None
    requires_human_review: bool = False
    active_patch_set_id: Optional[str] = None
    final_response: Optional[str] = None
    applied_patch_set_id: Optional[str] = None
    applied_patch_id: Optional[str] = None
    applied_document_id: Optional[str] = None
    applied_content: Optional[str] = None
    applied_version: Optional[int] = None
    trace_metadata: dict[str, Any] = Field(default_factory=dict)


class CopilotPatchOut(Schema):
    patch_id: str
    patch_set_id: Optional[str] = None
    run_id: str
    target_document_id: str
    base_version: int
    order_index: int = 0
    patch_type: str
    operation_type: str
    anchor: dict[str, Any] = Field(default_factory=dict)
    expected_hash: Optional[str] = None
    old_text: Optional[str] = None
    new_text: Optional[str] = None
    resolved_start: Optional[int] = None
    resolved_end: Optional[int] = None
    confidence: Optional[float] = None
    conflict_reason: Optional[str] = None
    before_preview: Optional[str] = None
    after_preview: Optional[str] = None
    document_preview_after: Optional[str] = None
    content_preview: str
    rationale: Optional[str] = None
    source_context_document_ids: list[str] = Field(default_factory=list)
    target_document_title: Optional[str] = None
    target_selection_reason: Optional[str] = None
    status: Literal["pending", "accepted", "rejected", "conflicted", "applied", "stale"]
    review_comment: Optional[str] = None
    # Sección semántica dentro de la nota clínica a la que pertenece este patch.
    # Derivada del clinical_plan del copiloto (ej. 'antecedentes_relevantes', 'plan').
    section: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class CopilotPatchSetOut(Schema):
    patch_set_id: str
    run_id: str
    target_document_id: str
    base_version: int
    base_hash: str
    rationale: Optional[str] = None
    source_context_document_ids: list[str] = Field(default_factory=list)
    target_document_title: Optional[str] = None
    target_selection_reason: Optional[str] = None
    document_preview_after: Optional[str] = None
    status: Literal[
        "pending",
        "partially_accepted",
        "accepted",
        "rejected",
        "stale",
        "applied",
    ]
    review_comment: Optional[str] = None
    patches: list[CopilotPatchOut] = Field(default_factory=list)
    # Campos del plan clínico emitidos por el copiloto vía set_edit_plan.
    # Persisten desde el agente para que el frontend muestre badge de alcance
    # y para que el auditor clínico pueda filtrar revisiones por impacto.
    edit_scope: Optional[str] = None
    clinical_impact_level: Optional[str] = None
    affected_sections: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class CopilotReviewIn(Schema):
    patch_id: str
    decision: Literal["approve", "reject"]
    comment: Optional[str] = None
    document_version: Optional[int] = None


class CopilotPatchDecisionIn(Schema):
    patch_id: str
    comment: Optional[str] = None


class CopilotPatchSetDecisionIn(Schema):
    comment: Optional[str] = None
    document_version: Optional[int] = None


class CopilotEventOut(Schema):
    sequence: int
    event: str
    run_id: str
    thread_id: str
    created_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class CopilotRunEventsOut(Schema):
    events: list[CopilotEventOut]
    status: str
    next_after_sequence: int
    done: bool


class CopilotInternalToolRequest(Schema):
    run_id: str
    thread_id: str
    encounter_id: int
    user_id: int


class CopilotListOpenDocumentsIn(CopilotInternalToolRequest):
    workspace_index: WorkspaceIndexIn


class CopilotToolDocumentOut(Schema):
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
    short_summary: Optional[str] = None


class CopilotListOpenDocumentsOut(Schema):
    documents: list[CopilotToolDocumentOut] = Field(default_factory=list)


class CopilotReadDocumentIn(CopilotInternalToolRequest):
    document_id: int
    mode: Literal["full"] = "full"


class CopilotReadDocumentOut(Schema):
    document_id: str
    encounter_id: str
    title: str
    type: str
    version: int
    content_hash: str
    updated_at: str
    mode: Literal["full"]
    content: Optional[str] = None


class CopilotSearchDocumentsIn(CopilotInternalToolRequest):
    query: str
    max_results: int = Field(default=3, ge=1, le=10)
    allowed_document_types: list[str] = Field(default_factory=list)


class CopilotSearchDocumentMatchOut(Schema):
    document_id: str
    title: str
    type: str
    updated_at: str
    snippet: str
    score: float
    anchor: dict[str, Any] = Field(default_factory=dict)


class CopilotSearchDocumentsOut(Schema):
    query: str
    matches: list[CopilotSearchDocumentMatchOut] = Field(default_factory=list)


class CopilotListEncounterDocumentsIn(CopilotInternalToolRequest):
    pass


class CopilotListEncounterDocumentsOut(Schema):
    documents: list[CopilotToolDocumentOut] = Field(default_factory=list)


class CopilotReadDocumentSummaryIn(CopilotInternalToolRequest):
    document_id: int


class CopilotReadDocumentSummaryOut(Schema):
    document_id: str
    encounter_id: str
    title: str
    type: str
    version: int
    content_hash: str
    updated_at: str
    short_summary: Optional[str] = None


class CopilotReadDocumentSpanIn(CopilotInternalToolRequest):
    document_id: int
    exact_text: Optional[str] = None
    prefix_text: Optional[str] = None
    suffix_text: Optional[str] = None
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None
    max_chars: int = Field(default=600, ge=1, le=20000)


class CopilotReadDocumentSpanOut(Schema):
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


class CopilotPatchHistoryItemOut(Schema):
    patch_id: str
    operation_type: str
    status: str
    rationale: Optional[str] = None
    created_at: datetime


class CopilotReadPatchHistoryOut(Schema):
    document_id: str
    patches: list[CopilotPatchHistoryItemOut] = Field(default_factory=list)


class CopilotReadEncounterContextIn(CopilotInternalToolRequest):
    pass


class CopilotEncounterContextOut(Schema):
    encounter_id: str
    encounter_name: Optional[str] = None
    occurred_at: Optional[str] = None
    has_been_transcribed: bool = False
    patient_id: Optional[str] = None
    patient_summary: Optional[str] = None
