from __future__ import annotations

import uuid
from typing import Any, Protocol, Sequence
from xml.sax.saxutils import escape

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime
from langgraph.types import Command
from pydantic import BaseModel, Field

from app.graph.state import CopilotState
from app.planner import CopilotPlanner, DraftedPatchPlan


class LayeredToolsClient(Protocol):
    def list_open_documents(self, workspace_index: dict[str, Any]) -> dict[str, Any]: ...

    def list_encounter_documents(self) -> dict[str, Any]: ...

    def read_document_summary(self, document_id: str) -> dict[str, Any]: ...

    def read_document_span(
        self,
        document_id: str,
        *,
        exact_text: str | None = None,
        prefix_text: str | None = None,
        suffix_text: str | None = None,
        start_offset: int | None = None,
        end_offset: int | None = None,
        max_chars: int = 600,
    ) -> dict[str, Any]: ...

    def search_documents(
        self,
        *,
        query: str,
        max_results: int = 3,
        allowed_document_types: list[str] | None = None,
    ) -> dict[str, Any]: ...

    def read_patch_history(self, document_id: str, *, limit: int = 5) -> dict[str, Any]: ...

    def build_context_view(
        self,
        *,
        active_document_id: str | None = None,
        include_document_ids: list[str] | None = None,
        include_manual_context: bool = True,
    ) -> dict[str, Any]: ...


PATCH_REQUIRED_FIELDS = {
    "patch_id",
    "target_document_id",
    "target_document_title",
    "target_selection_reason",
    "base_version",
    "operation_type",
    "content_preview",
}


class ListOpenDocumentsInput(BaseModel):
    pass


class ListEncounterDocumentsInput(BaseModel):
    pass


class ReadDocumentSummaryInput(BaseModel):
    document_id: str = Field(..., min_length=1)


class ReadDocumentSpanInput(BaseModel):
    document_id: str = Field(..., min_length=1)
    exact_text: str | None = None
    prefix_text: str | None = None
    suffix_text: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    max_chars: int = Field(default=2000, ge=1, le=20000)


class SearchDocumentsInput(BaseModel):
    query: str = Field(..., min_length=1)
    max_results: int = Field(default=3, ge=1, le=5)
    allowed_document_types: list[str] | None = None


class ReadPatchHistoryInput(BaseModel):
    document_id: str = Field(..., min_length=1)
    limit: int = Field(default=5, ge=1, le=10)


class BuildContextViewInput(BaseModel):
    active_document_id: str | None = None
    include_document_ids: list[str] | None = None
    include_manual_context: bool = True


class ProposePatchInput(BaseModel):
    target_document_id: str = Field(..., min_length=1)


class ProposeCreateDocumentInput(BaseModel):
    pass


def _shorten_text(value: Any, *, max_length: int = 320) -> str:
    if value is None:
        return ""
    text = " ".join(str(value).split())
    return text[:max_length]


def _xml_line(tag: str, value: Any, *, max_length: int = 320) -> str:
    return f"<{tag}>{escape(_shorten_text(value, max_length=max_length))}</{tag}>"


def _summarize_tool_result(tool_name: str, payload: dict[str, Any]) -> str:
    if tool_name == "list_open_documents":
        return f"{len(payload.get('documents', []))} document(s) abiertos disponibles"
    if tool_name == "list_encounter_documents":
        return f"{len(payload.get('documents', []))} document(s) totales del encounter"
    if tool_name == "read_document_summary":
        return f"Resumen del documento {payload.get('document_id')} cargado"
    if tool_name == "read_document_span":
        return f"Span focalizado leido de {payload.get('document_id')}"
    if tool_name == "search_documents":
        return f"{len(payload.get('matches', []))} coincidencia(s) relevantes"
    if tool_name == "read_patch_history":
        return f"Historial de {len(payload.get('patches', []))} patch(es)"
    if tool_name == "build_context_view":
        return f"Vista de contexto con {len(payload.get('facts', []))} fact(s)"
    if tool_name.startswith("propose_"):
        return f"Patch set listo para {payload.get('target_document_id')}"
    return "resultado de tool procesado"


def _build_retrieved_context(
    *,
    context_view: dict[str, Any] | None,
    read_documents: Sequence[dict[str, Any]],
    read_spans: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    context_items = [
        {
            "type": "context_fact",
            "document_id": fact["source_document_id"],
            "title": f"Fact {index + 1}",
            "excerpt": fact["value"],
            "read_mode": "context_view",
        }
        for index, fact in enumerate((context_view or {}).get("facts") or [])
    ]
    document_items = [
        {
            "type": document.get("type", "document"),
            "document_id": document["document_id"],
            "title": document.get("title"),
            "excerpt": _shorten_text(document.get("content") or document.get("excerpt")),
            "read_mode": document.get("mode"),
        }
        for document in read_documents
    ]
    span_items = [
        {
            "type": span.get("type", "document_span"),
            "document_id": span["document_id"],
            "title": span.get("title"),
            "excerpt": _shorten_text(span.get("content"), max_length=480),
            "read_mode": "span",
        }
        for span in read_spans
    ]
    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for item in [*context_items, *document_items, *span_items]:
        key = (
            str(item.get("document_id") or ""),
            str(item.get("read_mode") or ""),
            str(item.get("excerpt") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _upsert_read_document(
    current: Sequence[dict[str, Any]],
    document: dict[str, Any],
) -> list[dict[str, Any]]:
    document_id = str(document["document_id"])
    remaining = [
        existing
        for existing in current
        if str(existing["document_id"]) != document_id or existing.get("mode") != document.get("mode")
    ]
    return [*remaining, document]


def _upsert_read_span(
    current: Sequence[dict[str, Any]],
    span: dict[str, Any],
) -> list[dict[str, Any]]:
    document_id = str(span["document_id"])
    remaining = [
        existing
        for existing in current
        if not (
            str(existing["document_id"]) == document_id
            and existing.get("start_offset") == span.get("start_offset")
            and existing.get("end_offset") == span.get("end_offset")
        )
    ]
    return [*remaining, span]


def _append_state_items(
    current: Sequence[dict[str, Any]] | None,
    updates: Sequence[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    return [*(current or []), *(updates or [])]


def _default_selected_document_ids(state: CopilotState) -> list[str]:
    available_documents = state.get("available_documents") or []
    available_ids = {str(document["document_id"]) for document in available_documents}
    explicit_selection = [
        document_id
        for document_id in state.get("selected_document_ids", [])
        if document_id in available_ids
    ]
    if explicit_selection:
        return explicit_selection

    open_selection = [
        str(document["document_id"])
        for document in available_documents
        if document.get("is_active") or document.get("pinned_for_agent")
    ]
    if open_selection:
        return open_selection
    return [str(document["document_id"]) for document in available_documents[:2]]


def _tool_observation_content(
    tool_name: str,
    summary: str,
    payload: dict[str, Any],
    *,
    is_error: bool = False,
) -> str:
    lines = [
        f'<tool_observation name="{escape(tool_name)}" status="{"error" if is_error else "success"}">',
        f"  {_xml_line('summary', summary)}",
    ]
    if is_error:
        lines.append(f"  {_xml_line('error', payload.get('error'))}")
    elif tool_name in {"read_document_summary", "read_document_span"}:
        lines.append(f"  {_xml_line('document_id', payload.get('document_id'))}")
        lines.append(f"  {_xml_line('title', payload.get('title'))}")
        lines.append(f"  {_xml_line('excerpt', payload.get('excerpt') or payload.get('content'), max_length=900)}")
    elif tool_name in {"list_open_documents", "list_encounter_documents"}:
        for document in (payload.get("documents") or [])[:6]:
            lines.append("  <document>")
            lines.append(f"    {_xml_line('document_id', document.get('document_id'))}")
            lines.append(f"    {_xml_line('title', document.get('title'))}")
            lines.append(f"    {_xml_line('type', document.get('type'))}")
            lines.append(f"    {_xml_line('ai_writable', document.get('ai_writable'))}")
            lines.append("  </document>")
    elif tool_name == "search_documents":
        for match in (payload.get("matches") or [])[:4]:
            lines.append("  <match>")
            lines.append(f"    {_xml_line('document_id', match.get('document_id'))}")
            lines.append(f"    {_xml_line('title', match.get('title'))}")
            lines.append(f"    {_xml_line('snippet', match.get('snippet'))}")
            lines.append("  </match>")
    elif tool_name == "build_context_view":
        for fact in (payload.get("facts") or [])[:6]:
            lines.append("  <fact>")
            lines.append(f"    {_xml_line('category', fact.get('category'))}")
            lines.append(f"    {_xml_line('value', fact.get('value'))}")
            lines.append(f"    {_xml_line('source_document_id', fact.get('source_document_id'))}")
            lines.append("  </fact>")
    elif tool_name == "read_patch_history":
        for patch in (payload.get("patches") or [])[:5]:
            lines.append("  <patch>")
            lines.append(f"    {_xml_line('patch_id', patch.get('patch_id'))}")
            lines.append(f"    {_xml_line('status', patch.get('status'))}")
            lines.append(f"    {_xml_line('operation_type', patch.get('operation_type'))}")
            lines.append("  </patch>")
    elif tool_name.startswith("propose_"):
        lines.append(f"  {_xml_line('patch_set_id', payload.get('patch_set_id'))}")
        lines.append(f"  {_xml_line('target_document_id', payload.get('target_document_id'))}")
        lines.append(f"  {_xml_line('rationale', payload.get('rationale'))}")
        for patch in (payload.get("patches") or [])[:6]:
            lines.append("  <patch>")
            lines.append(f"    {_xml_line('patch_id', patch.get('patch_id'))}")
            lines.append(f"    {_xml_line('operation_type', patch.get('operation_type'))}")
            lines.append(f"    {_xml_line('rationale', patch.get('rationale'))}")
            lines.append("  </patch>")
    lines.append("</tool_observation>")
    return "\n".join(lines)


def _success_command(
    *,
    state: CopilotState,
    tool_name: str,
    tool_call_id: str,
    payload: dict[str, Any],
    updates: dict[str, Any],
) -> Command:
    summary = _summarize_tool_result(tool_name, payload)
    return Command(
        update={
            **updates,
            "last_tool_error": None,
            "tool_results": _append_state_items(
                state.get("tool_results"),
                [
                    {
                        "tool_name": tool_name,
                        "summary": summary,
                        "payload": payload,
                    }
                ],
            ),
            "messages": [
                ToolMessage(
                    tool_call_id=tool_call_id,
                    name=tool_name,
                    content=_tool_observation_content(tool_name, summary, payload),
                    artifact=payload,
                    status="success",
                )
            ],
        }
    )


def _error_command(
    *,
    state: CopilotState,
    tool_name: str,
    tool_call_id: str,
    error_message: str,
    updates: dict[str, Any] | None = None,
) -> Command:
    payload = {"error": error_message}
    return Command(
        update={
            **(updates or {}),
            "last_tool_error": error_message,
            "tool_results": _append_state_items(
                state.get("tool_results"),
                [
                    {
                        "tool_name": tool_name,
                        "summary": error_message,
                        "payload": payload,
                    }
                ],
            ),
            "messages": [
                ToolMessage(
                    tool_call_id=tool_call_id,
                    name=tool_name,
                    content=_tool_observation_content(
                        tool_name,
                        error_message,
                        payload,
                        is_error=True,
                    ),
                    artifact=payload,
                    status="error",
                )
            ],
        }
    )


def _runtime_parts(
    runtime: ToolRuntime,
    *,
    tool_name: str,
) -> tuple[CopilotState, str]:
    # ToolRuntime keeps state/tool_call_id out of the public tool schema that the LLM
    # sees, while still letting our Command/ToolMessage helpers stay small and explicit.
    state = runtime.state
    tool_call_id = runtime.tool_call_id or f"{tool_name}-runtime"
    return state, tool_call_id


def _find_document(
    state: CopilotState,
    *,
    document_id: str,
) -> dict[str, Any] | None:
    for document in state.get("available_documents") or state.get("workspace_index", {}).get(
        "documents",
        [],
    ):
        if str(document.get("document_id")) == str(document_id):
            return document

    summary = _current_summary(state, document_id=document_id)
    if summary:
        return {
            "document_id": str(summary.get("document_id") or document_id),
            "title": summary.get("title"),
            "type": summary.get("type"),
            "version": summary.get("version"),
            "ai_writable": True,
            "is_active": str(state.get("active_document_id") or "") == str(document_id),
        }

    span = _current_span(state, document_id=document_id)
    if span:
        return {
            "document_id": str(span.get("document_id") or document_id),
            "title": span.get("title"),
            "type": span.get("type"),
            "version": span.get("version"),
            "ai_writable": True,
            "is_active": str(state.get("active_document_id") or "") == str(document_id),
        }

    workspace_index = state.get("workspace_index") or {}
    if str(workspace_index.get("active_document_id") or "") == str(document_id) or str(
        document_id
    ) in {str(item) for item in workspace_index.get("open_document_ids") or []}:
        return {
            "document_id": str(document_id),
            "title": f"Document {document_id}",
            "type": "note",
            "version": None,
            "ai_writable": True,
            "is_active": str(workspace_index.get("active_document_id") or "")
            == str(document_id),
        }
    return None


def _current_summary(
    state: CopilotState,
    *,
    document_id: str,
) -> dict[str, Any] | None:
    summaries = state.get("document_summaries") or {}
    return summaries.get(str(document_id))


def _current_span(
    state: CopilotState,
    *,
    document_id: str,
) -> dict[str, Any] | None:
    for span in state.get("read_spans") or []:
        if str(span.get("document_id")) == str(document_id):
            return span
    return None


def _selection_reason(state: CopilotState, *, target_document_id: str) -> str:
    if str(state.get("active_document_id") or "") == str(target_document_id):
        return "llm_target_document_id, active_document"
    return "llm_target_document_id"


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


def _build_patch_set_preview_payload(
    *,
    state: CopilotState,
    drafted_plan: DraftedPatchPlan,
    target_document: dict[str, Any],
    summary_payload: dict[str, Any],
    span_payload: dict[str, Any],
) -> dict[str, Any]:
    target_document_id = str(target_document["document_id"])
    target_document_title = str(
        summary_payload.get("title") or target_document.get("title") or target_document_id
    )
    source_context_document_ids = sorted(
        {
            str(item.get("document_id"))
            for item in _build_retrieved_context(
                context_view=state.get("context_view"),
                read_documents=state.get("read_documents") or [],
                read_spans=state.get("read_spans") or [],
            )
            if item.get("document_id")
        }
    )
    base_version = int(
        summary_payload.get("version")
        or span_payload.get("version")
        or target_document.get("version")
        or 1
    )
    selection_reason = _selection_reason(state, target_document_id=target_document_id)
    patches: list[dict[str, Any]] = []
    for index, patch in enumerate(drafted_plan.patches):
        document_preview_after = (
            patch.document_preview_after
            or drafted_plan.document_preview_after
            or patch.content_preview
        )
        patches.append(
            {
                "patch_id": str(uuid.uuid4()),
                "patch_type": patch.operation_type,
                "operation_type": patch.operation_type,
                "order_index": index,
                "anchor": patch.anchor.to_payload(),
                "expected_hash": patch.expected_hash,
                "old_text": patch.before_preview,
                "new_text": patch.after_preview,
                "before_preview": patch.before_preview,
                "after_preview": patch.after_preview,
                "document_preview_after": document_preview_after,
                "content_preview": patch.content_preview,
                "rationale": patch.rationale,
                "confidence": patch.confidence,
                "target_document_id": target_document_id,
                "target_document_title": target_document_title,
                "target_selection_reason": selection_reason,
                "base_version": base_version,
                "source_context_document_ids": source_context_document_ids,
            }
        )

    return {
        "patch_set_id": str(uuid.uuid4()),
        "target_document_id": target_document_id,
        "target_document_title": target_document_title,
        "target_selection_reason": selection_reason,
        "base_version": base_version,
        "base_hash": summary_payload.get("content_hash") or span_payload.get("content_hash"),
        "rationale": drafted_plan.rationale,
        "document_preview_after": drafted_plan.document_preview_after,
        "source_context_document_ids": source_context_document_ids,
        "patches": patches,
    }


def build_graph_tools(
    *,
    tools_client: LayeredToolsClient,
    planner: CopilotPlanner,
):
    @tool
    def list_open_documents(
        runtime: ToolRuntime,
    ) -> Command:
        """List the currently open workspace documents."""
        state, tool_call_id = _runtime_parts(
            runtime,
            tool_name="list_open_documents",
        )
        try:
            payload = tools_client.list_open_documents(state["workspace_index"])
        except Exception as error:
            return _error_command(
                state=state,
                tool_name="list_open_documents",
                tool_call_id=tool_call_id,
                error_message=f"No pude listar los documentos abiertos: {error}",
            )

        documents = payload.get("documents", [])
        return _success_command(
            state=state,
            tool_name="list_open_documents",
            tool_call_id=tool_call_id,
            payload=payload,
            updates={
                "available_documents": documents,
                "selected_document_ids": _default_selected_document_ids(
                    {
                        **state,
                        "available_documents": documents,
                    }
                ),
            },
        )

    @tool
    def list_encounter_documents(
        runtime: ToolRuntime,
    ) -> Command:
        """List every document available for the encounter."""
        state, tool_call_id = _runtime_parts(
            runtime,
            tool_name="list_encounter_documents",
        )
        try:
            payload = tools_client.list_encounter_documents()
        except Exception as error:
            return _error_command(
                state=state,
                tool_name="list_encounter_documents",
                tool_call_id=tool_call_id,
                error_message=f"No pude listar los documentos del encounter: {error}",
            )

        documents = payload.get("documents", [])
        return _success_command(
            state=state,
            tool_name="list_encounter_documents",
            tool_call_id=tool_call_id,
            payload=payload,
            updates={"available_documents": documents},
        )

    @tool
    def read_document_summary(
        document_id: str,
        runtime: ToolRuntime,
    ) -> Command:
        """Read a concise summary for one document."""
        state, tool_call_id = _runtime_parts(
            runtime,
            tool_name="read_document_summary",
        )
        validated = ReadDocumentSummaryInput(document_id=document_id)
        try:
            payload = tools_client.read_document_summary(validated.document_id)
        except Exception as error:
            return _error_command(
                state=state,
                tool_name="read_document_summary",
                tool_call_id=tool_call_id,
                error_message=(
                    f"No pude leer el resumen del documento {validated.document_id}: {error}"
                ),
            )

        summary_map = {
            **(state.get("document_summaries") or {}),
            str(payload["document_id"]): payload,
        }
        read_documents = _upsert_read_document(
            state.get("read_documents") or [],
            {
                "document_id": payload["document_id"],
                "title": payload.get("title"),
                "type": payload.get("type"),
                "mode": "summary",
                "excerpt": payload.get("excerpt"),
                "content": None,
                "content_hash": payload.get("content_hash"),
            },
        )
        return _success_command(
            state=state,
            tool_name="read_document_summary",
            tool_call_id=tool_call_id,
            payload=payload,
            updates={
                "document_summaries": summary_map,
                "read_documents": read_documents,
                "retrieved_context": _build_retrieved_context(
                    context_view=state.get("context_view"),
                    read_documents=read_documents,
                    read_spans=state.get("read_spans") or [],
                ),
            },
        )

    @tool
    def read_document_span(
        document_id: str,
        runtime: ToolRuntime,
        exact_text: str | None = None,
        prefix_text: str | None = None,
        suffix_text: str | None = None,
        start_offset: int | None = None,
        end_offset: int | None = None,
        max_chars: int = 4000,
    ) -> Command:
        """Read a focused span from one document."""
        state, tool_call_id = _runtime_parts(
            runtime,
            tool_name="read_document_span",
        )
        safe_max_chars = min(max_chars, 20000)
        validated = ReadDocumentSpanInput(
            document_id=document_id,
            exact_text=exact_text,
            prefix_text=prefix_text,
            suffix_text=suffix_text,
            start_offset=start_offset,
            end_offset=end_offset,
            max_chars=safe_max_chars,
        )
        try:
            payload = tools_client.read_document_span(
                validated.document_id,
                exact_text=validated.exact_text,
                prefix_text=validated.prefix_text,
                suffix_text=validated.suffix_text,
                start_offset=validated.start_offset,
                end_offset=validated.end_offset,
                max_chars=validated.max_chars,
            )
        except Exception as error:
            return _error_command(
                state=state,
                tool_name="read_document_span",
                tool_call_id=tool_call_id,
                error_message=(
                    f"No pude leer el span del documento {validated.document_id}: {error}"
                ),
            )

        summary_payload = _current_summary(state, document_id=document_id) or {}
        span_payload = {
            **payload,
            "title": payload.get("title") or summary_payload.get("title"),
            "type": payload.get("type") or summary_payload.get("type"),
        }
        read_spans = _upsert_read_span(state.get("read_spans") or [], span_payload)
        read_documents = _upsert_read_document(
            state.get("read_documents") or [],
            {
                "document_id": span_payload["document_id"],
                "title": span_payload.get("title"),
                "type": span_payload.get("type"),
                "mode": "span",
                "content": span_payload.get("content"),
                "excerpt": _shorten_text(span_payload.get("content"), max_length=480),
                "content_hash": span_payload.get("content_hash"),
            },
        )
        return _success_command(
            state=state,
            tool_name="read_document_span",
            tool_call_id=tool_call_id,
            payload=span_payload,
            updates={
                "read_spans": read_spans,
                "read_documents": read_documents,
                "retrieved_context": _build_retrieved_context(
                    context_view=state.get("context_view"),
                    read_documents=read_documents,
                    read_spans=read_spans,
                ),
            },
        )

    @tool
    def search_documents(
        query: str,
        runtime: ToolRuntime,
        max_results: int = 3,
        allowed_document_types: list[str] | None = None,
    ) -> Command:
        """Search across encounter documents for relevant snippets."""
        state, tool_call_id = _runtime_parts(
            runtime,
            tool_name="search_documents",
        )
        validated = SearchDocumentsInput(
            query=query,
            max_results=max_results,
            allowed_document_types=allowed_document_types,
        )
        try:
            payload = tools_client.search_documents(
                query=validated.query,
                max_results=validated.max_results,
                allowed_document_types=validated.allowed_document_types,
            )
        except Exception as error:
            return _error_command(
                state=state,
                tool_name="search_documents",
                tool_call_id=tool_call_id,
                error_message=f"No pude buscar documentos relevantes: {error}",
            )

        return _success_command(
            state=state,
            tool_name="search_documents",
            tool_call_id=tool_call_id,
            payload=payload,
            updates={
                "search_query": payload.get("query"),
                "search_matches": payload.get("matches", []),
            },
        )

    @tool
    def read_patch_history(
        document_id: str,
        runtime: ToolRuntime,
        limit: int = 5,
    ) -> Command:
        """Read recent patch history for one document."""
        state, tool_call_id = _runtime_parts(
            runtime,
            tool_name="read_patch_history",
        )
        validated = ReadPatchHistoryInput(document_id=document_id, limit=limit)
        try:
            payload = tools_client.read_patch_history(
                validated.document_id,
                limit=validated.limit,
            )
        except Exception as error:
            return _error_command(
                state=state,
                tool_name="read_patch_history",
                tool_call_id=tool_call_id,
                error_message=(
                    f"No pude leer el historial de patches de {validated.document_id}: {error}"
                ),
            )

        return _success_command(
            state=state,
            tool_name="read_patch_history",
            tool_call_id=tool_call_id,
            payload=payload,
            updates={
                "patch_history": {
                    **(state.get("patch_history") or {}),
                    str(payload["document_id"]): payload.get("patches", []),
                }
            },
        )

    @tool
    def build_context_view(
        runtime: ToolRuntime,
        active_document_id: str | None = None,
        include_document_ids: list[str] | None = None,
        include_manual_context: bool = True,
    ) -> Command:
        """Build a synthesized context view from the current workspace."""
        state, tool_call_id = _runtime_parts(
            runtime,
            tool_name="build_context_view",
        )
        validated = BuildContextViewInput(
            active_document_id=active_document_id,
            include_document_ids=include_document_ids,
            include_manual_context=include_manual_context,
        )
        try:
            payload = tools_client.build_context_view(
                active_document_id=validated.active_document_id
                or state.get("active_document_id"),
                include_document_ids=validated.include_document_ids
                or state.get("selected_document_ids", []),
                include_manual_context=validated.include_manual_context,
            )
        except Exception as error:
            return _error_command(
                state=state,
                tool_name="build_context_view",
                tool_call_id=tool_call_id,
                error_message=f"No pude construir la vista de contexto: {error}",
            )

        return _success_command(
            state=state,
            tool_name="build_context_view",
            tool_call_id=tool_call_id,
            payload=payload,
            updates={
                "context_view": payload,
                "retrieved_context": _build_retrieved_context(
                    context_view=payload,
                    read_documents=state.get("read_documents") or [],
                    read_spans=state.get("read_spans") or [],
                ),
            },
        )

    def _propose_patch(
        *,
        state: CopilotState,
        tool_call_id: str,
        tool_name: str,
        target_document_id: str,
    ) -> Command:
        if int(state.get("patch_operations_count") or 0) >= int(
            state.get("max_patch_operations") or 1
        ):
            return _error_command(
                state=state,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                error_message=(
                    "El run ya consumio el presupuesto maximo de operaciones de patch."
                ),
            )

        target_document = _find_document(state, document_id=target_document_id)
        if not target_document:
            return _error_command(
                state=state,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                error_message=(
                    f"El documento target {target_document_id} no existe en el workspace actual."
                ),
            )
        if target_document.get("ai_writable") is False:
            return _error_command(
                state=state,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                error_message=(
                    f"El documento target {target_document_id} no es editable por el copiloto."
                ),
            )

        summary_payload = _current_summary(state, document_id=target_document_id)
        if not summary_payload:
            return _error_command(
                state=state,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                error_message=(
                    "Antes de proponer un patch debes leer el resumen del documento target "
                    "con read_document_summary."
                ),
            )
        span_payload = _current_span(state, document_id=target_document_id)
        if not span_payload:
            return _error_command(
                state=state,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                error_message=(
                    "Antes de proponer un patch debes leer un span del documento target "
                    "con read_document_span."
                ),
            )

        try:
            drafted_plan = planner.draft_patch_preview(
                state=state,
                target_document=target_document,
                target_document_content=str(span_payload.get("content") or ""),
                supporting_context=_build_retrieved_context(
                    context_view=state.get("context_view"),
                    read_documents=state.get("read_documents") or [],
                    read_spans=state.get("read_spans") or [],
                ),
                span_payload=span_payload,
                requested_tool_name=tool_name,
            )
        except Exception as error:
            return _error_command(
                state=state,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                error_message=f"No pude redactar un patch clinico seguro: {error}",
            )

        if not drafted_plan.patches:
            return _error_command(
                state=state,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                error_message=(
                    "No se pudo redactar un patch clinico revisable para esta solicitud. "
                    "El LLM no devolvio cambios materializados."
                ),
            )

        payload = _build_patch_set_preview_payload(
            state=state,
            drafted_plan=drafted_plan,
            target_document=target_document,
            summary_payload=summary_payload,
            span_payload=span_payload,
        )
        if not _is_valid_patch_set_preview(payload):
            return _error_command(
                state=state,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                error_message=(
                    "El runtime no pudo construir un patch set revisable con metadata completa."
                ),
            )

        first_patch = payload["patches"][0]
        return _success_command(
            state=state,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            payload=payload,
            updates={
                "target_document_id": payload["target_document_id"],
                "target_document_title": payload["target_document_title"],
                "target_selection_reason": payload["target_selection_reason"],
                "base_version": payload["base_version"],
                "patch_set_preview": payload,
                # Keep the first patch mirrored for the legacy frontend review card
                # until the full PatchSet UI becomes the only review surface.
                "patch_preview": first_patch,
                "patch_id": first_patch["patch_id"],
                "requires_human_review": True,
                "final_response": None,
                "patch_operations_count": int(state.get("patch_operations_count") or 0)
                + 1,
            },
        )

    @tool
    def propose_replace_span(
        target_document_id: str,
        runtime: ToolRuntime,
    ) -> Command:
        """Draft a reviewable patch set centered on span replacement.

        Sequential precondition: call this only after `read_document_summary` and
        `read_document_span` have already completed for the same target document in
        earlier turns. Never call this in the same turn as read tools.
        """
        state, tool_call_id = _runtime_parts(
            runtime,
            tool_name="propose_replace_span",
        )
        validated = ProposePatchInput(target_document_id=target_document_id)
        return _propose_patch(
            state=state,
            tool_call_id=tool_call_id,
            tool_name="propose_replace_span",
            target_document_id=validated.target_document_id,
        )

    @tool
    def propose_insert_after_span(
        target_document_id: str,
        runtime: ToolRuntime,
    ) -> Command:
        """Draft a reviewable patch set centered on anchored insertion.

        Sequential precondition: call this only after `read_document_summary` and
        `read_document_span` have already completed for the same target document in
        earlier turns. Never call this in the same turn as read tools.
        """
        state, tool_call_id = _runtime_parts(
            runtime,
            tool_name="propose_insert_after_span",
        )
        validated = ProposePatchInput(target_document_id=target_document_id)
        return _propose_patch(
            state=state,
            tool_call_id=tool_call_id,
            tool_name="propose_insert_after_span",
            target_document_id=validated.target_document_id,
        )

    @tool
    def propose_create_document(
        runtime: ToolRuntime,
    ) -> Command:
        """Explain that new document creation is not enabled in this runtime yet."""
        state, tool_call_id = _runtime_parts(
            runtime,
            tool_name="propose_create_document",
        )
        return _error_command(
            state=state,
            tool_name="propose_create_document",
            tool_call_id=tool_call_id,
            error_message=(
                "La creacion de documentos nuevos todavia no esta habilitada en este runtime. "
                "Elige un documento existente o responde con la limitacion de forma explicita."
            ),
        )

    return [
        list_open_documents,
        list_encounter_documents,
        read_document_summary,
        read_document_span,
        search_documents,
        read_patch_history,
        build_context_view,
        propose_replace_span,
        propose_insert_after_span,
        propose_create_document,
    ]
