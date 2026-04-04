from __future__ import annotations

import uuid
from typing import Any, Literal, Protocol, Sequence
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

    def read_document(
        self,
        document_id: str,
        *,
        mode: str = "excerpt",
    ) -> dict[str, Any]: ...

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

PATCH_REQUIRED_FIELDS = {
    "patch_id",
    "target_document_id",
    "target_document_title",
    "target_selection_reason",
    "base_version",
    "operation_type",
    "content_preview",
}

# Presupuesto máximo de patches permitido por scope clínico.
# local: una sección, un cambio delimitado.
# propagation: el mismo dato clínico debe reflejarse en varias secciones (hasta 5).
# reinterpretation: el dato cambia diagnóstico, análisis, riesgo o plan (hasta 8).
_MAX_PATCH_OPERATIONS_BY_SCOPE: dict[str, int] = {
    "local": 1,
    "propagation": 5,
    "reinterpretation": 8,
}


def _patch_field_is_present(patch_preview: dict[str, Any], field_name: str) -> bool:
    if field_name == "content_preview":
        if str(patch_preview.get("operation_type") or "") == "delete_span":
            return "content_preview" in patch_preview
        value = patch_preview.get(field_name)
        return value is not None and str(value) != ""

    value = patch_preview.get(field_name)
    return value is not None and str(value) != ""


class ListOpenDocumentsInput(BaseModel):
    pass


class ListEncounterDocumentsInput(BaseModel):
    pass


class ReadDocumentSummaryInput(BaseModel):
    document_id: str = Field(..., min_length=1)


class ReadDocumentInput(BaseModel):
    document_id: str = Field(..., min_length=1)
    mode: Literal["summary", "excerpt", "full"] = "excerpt"


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
    if tool_name == "read_document":
        return (
            f"Documento {payload.get('document_id')} leido en modo "
            f"{payload.get('mode')}"
        )
    if tool_name == "read_document_summary":
        return f"Resumen del documento {payload.get('document_id')} cargado"
    if tool_name == "read_document_span":
        return f"Span focalizado leido de {payload.get('document_id')}"
    if tool_name == "search_documents":
        return f"{len(payload.get('matches', []))} coincidencia(s) relevantes"
    if tool_name == "read_patch_history":
        return f"Historial de {len(payload.get('patches', []))} patch(es)"
    if tool_name == "set_edit_plan":
        # Resumen de la clasificación clínica registrada por el planner.
        scope = payload.get("edit_scope", "local")
        sections = payload.get("affected_sections") or []
        max_ops = payload.get("max_patch_operations", 1)
        return (
            f"Plan clínico registrado: scope={scope}, "
            f"{len(sections)} sección(es) afectada(s), max_patches={max_ops}"
        )
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
            "excerpt": _shorten_text(
                document.get("content") or document.get("excerpt"),
                max_length=12000,
            ),
            "read_mode": document.get("mode"),
        }
        for document in read_documents
    ]
    span_items = [
        {
            "type": span.get("type", "document_span"),
            "document_id": span["document_id"],
            "title": span.get("title"),
            "excerpt": _shorten_text(span.get("content"), max_length=12000),
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
    elif tool_name in {"read_document", "read_document_summary", "read_document_span"}:
        lines.append(f"  {_xml_line('document_id', payload.get('document_id'))}")
        lines.append(f"  {_xml_line('title', payload.get('title'))}")
        if tool_name == "read_document":
            lines.append(f"  {_xml_line('mode', payload.get('mode'))}")
        # read_document_summary devuelve solo metadatos + excerpt corto (backend ya lo acota).
        # read_document(mode="full") y read_document_span pueden ser documentos largos;
        # usamos un límite alto para que el LLM los reciba completos.
        if tool_name == "read_document_summary":
            lines.append(f"  {_xml_line('excerpt', payload.get('excerpt') or payload.get('content'))}")
        else:
            lines.append(f"  {_xml_line('excerpt', payload.get('content') or payload.get('excerpt'), max_length=12000)}")
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
    elif tool_name == "read_patch_history":
        for patch in (payload.get("patches") or [])[:5]:
            lines.append("  <patch>")
            lines.append(f"    {_xml_line('patch_id', patch.get('patch_id'))}")
            lines.append(f"    {_xml_line('status', patch.get('status'))}")
            lines.append(f"    {_xml_line('operation_type', patch.get('operation_type'))}")
            lines.append("  </patch>")
    elif tool_name == "set_edit_plan":
        # Confirma al planner qué plan clínico registró y cuántos patches puede emitir.
        lines.append(f"  {_xml_line('edit_scope', payload.get('edit_scope'))}")
        lines.append(f"  {_xml_line('clinical_impact_level', payload.get('clinical_impact_level'))}")
        lines.append(
            f"  {_xml_line('affected_sections', ', '.join(payload.get('affected_sections') or []))}"
        )
        lines.append(f"  {_xml_line('needs_full_note', payload.get('needs_full_note'))}")
        lines.append(
            f"  {_xml_line('needs_external_knowledge', payload.get('needs_external_knowledge'))}"
        )
        lines.append(f"  {_xml_line('max_patch_operations', payload.get('max_patch_operations'))}")
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
            "tool_results": [
                {
                    "tool_name": tool_name,
                    "summary": summary,
                    "payload": payload,
                }
            ],
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
            "tool_results": [
                {
                    "tool_name": tool_name,
                    "summary": error_message,
                    "payload": payload,
                }
            ],
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

    document_read = _current_document_read(
        state,
        document_id=document_id,
        modes=("summary", "excerpt", "full"),
    )
    if document_read:
        return {
            "document_id": str(document_read.get("document_id") or document_id),
            "title": document_read.get("title"),
            "type": document_read.get("type"),
            "version": document_read.get("version"),
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


def _current_document_read(
    state: CopilotState,
    *,
    document_id: str,
    modes: Sequence[str] | None = None,
) -> dict[str, Any] | None:
    allowed_modes = {str(mode) for mode in (modes or [])}
    for document in state.get("document_reads") or []:
        if str(document.get("document_id")) != str(document_id):
            continue
        if allowed_modes and str(document.get("mode") or "") not in allowed_modes:
            continue
        return document
    return None


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


def _build_patch_set_preview_payload(
    *,
    state: CopilotState,
    drafted_plan: DraftedPatchPlan,
    target_document: dict[str, Any],
    summary_payload: dict[str, Any],
    span_payload: dict[str, Any] | None,
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
        or (span_payload or {}).get("version")
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
                # Sección semántica indicada por el drafter, derivada del clinical_plan.
                # Permite al frontend agrupar patches por sección y al auditor clínico
                # validar que el cambio quedó registrado en el lugar correcto.
                "section": patch.section,
                "target_document_id": target_document_id,
                "target_document_title": target_document_title,
                "target_selection_reason": selection_reason,
                "base_version": base_version,
                "source_context_document_ids": source_context_document_ids,
            }
        )

    # Adjuntar los campos del clinical_plan al patch_set_preview para que el backend
    # Django los persista en CopilotPatchSet y el frontend los pueda mostrar en la
    # tarjeta de revisión (ej. badge de alcance clínico).
    clinical_plan = state.get("clinical_plan") or {}
    return {
        "patch_set_id": str(uuid.uuid4()),
        "target_document_id": target_document_id,
        "target_document_title": target_document_title,
        "target_selection_reason": selection_reason,
        "base_version": base_version,
        "base_hash": summary_payload.get("content_hash")
        or (span_payload or {}).get("content_hash"),
        "rationale": drafted_plan.rationale,
        "document_preview_after": drafted_plan.document_preview_after,
        "source_context_document_ids": source_context_document_ids,
        "edit_scope": clinical_plan.get("edit_scope"),
        "clinical_impact_level": clinical_plan.get("clinical_impact_level"),
        "affected_sections": list(clinical_plan.get("affected_sections") or []),
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
        """
        Lista los documentos del workspace que el doctor tiene actualmente abiertos en pantalla.
        Útil para saber qué contexto está viendo el usuario ahora mismo o para inferir el
        documento destino si el doctor dice 'agrega esto al documento actual'.
        """
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
            },
        )

    @tool
    def list_encounter_documents(
        runtime: ToolRuntime,
    ) -> Command:
        """
        Lista absolutamente todos los documentos disponibles (fuentes, notas, historia clínica) en la consulta actual.
        Úsalo como primer paso SIEMPRE que te pidan leer o extraer información y NO sepas qué documentos existen,
        o para investigar cuál documento contiene el contexto vital que solicita el doctor. 
        Te devuelve los IDs, títulos y tipos de documentos. Úsalos para decidir qué documento leer o editar después.
        """
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
    def read_document(
        document_id: str,
        runtime: ToolRuntime,
        mode: Literal["summary", "excerpt", "full"] = "excerpt",
    ) -> Command:
        """
        Lee un documento completo o una version resumida/excerpt segun la necesidad.
        Usa `mode="summary"` para orientarte rapido, `mode="excerpt"` para una lectura
        ligera y `mode="full"` cuando necesites verificar estructura global, insertar
        al inicio/final o redactar cambios amplios sin depender de un span parcial.
        """
        state, tool_call_id = _runtime_parts(
            runtime,
            tool_name="read_document",
        )
        validated = ReadDocumentInput(document_id=document_id, mode=mode)
        try:
            payload = tools_client.read_document(
                validated.document_id,
                mode=validated.mode,
            )
        except Exception as error:
            return _error_command(
                state=state,
                tool_name="read_document",
                tool_call_id=tool_call_id,
                error_message=(
                    f"No pude leer el documento {validated.document_id} en modo "
                    f"{validated.mode}: {error}"
                ),
            )

        updates: dict[str, Any] = {
            "document_reads": [payload],
        }
        if payload.get("mode") == "summary":
            updates["document_summaries"] = {
                str(payload["document_id"]): payload,
            }

        return _success_command(
            state=state,
            tool_name="read_document",
            tool_call_id=tool_call_id,
            payload=payload,
            updates=updates,
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

        return _success_command(
            state=state,
            tool_name="read_document_summary",
            tool_call_id=tool_call_id,
            payload=payload,
            updates={
                "document_summaries": {
                    str(payload["document_id"]): payload,
                },
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
        return _success_command(
            state=state,
            tool_name="read_document_span",
            tool_call_id=tool_call_id,
            payload=span_payload,
            updates={
                "read_spans": [span_payload],
            },
        )

    @tool
    def search_documents(
        query: str,
        runtime: ToolRuntime,
        max_results: int = 3,
        allowed_document_types: list[str] | None = None,
    ) -> Command:
        """
        Búsqueda semántica (vectorial) de fragmentos relevantes en los documentos de la consulta médica.
        USO CORRECTO: Buscar términos médicos altamente específicos, especialidades, síntomas, medicamentos
        o años muy puntuales (ej. "hipertensión", "losartán 50mg", "cirugía de rodilla", "2015").
        ERROR GRAVE: Usarla para intenciones generales, buscar tipos documentales, metadatos estructurados
        o palabras abstractas como "nombre", "edad", "paciente", "datos", "resumen", "historia clínica".
        Si necesitas extraer el motivo general, el nombre del paciente, los datos demográficos o el
        contexto completo, NO uses esta herramienta; DEBES aprovechar directamente `read_document` 
        o `read_document_span` para leer la consulta en sí misma.
        """
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
                "search_results": [
                    {
                        "query": payload.get("query"),
                        "max_results": validated.max_results,
                        "allowed_document_types": validated.allowed_document_types or [],
                        "matches": payload.get("matches", []),
                    }
                ],
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

        summary_payload = _current_summary(state, document_id=target_document_id) or _current_document_read(
            state,
            document_id=target_document_id,
            modes=("summary", "excerpt", "full"),
        )
        if not summary_payload:
            return _error_command(
                state=state,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                error_message=(
                    "Antes de proponer un patch debes leer el documento target con "
                    "read_document(mode='summary'|'excerpt'|'full')."
                ),
            )
        span_payload = _current_span(state, document_id=target_document_id)
        full_document_payload = _current_document_read(
            state,
            document_id=target_document_id,
            modes=("full",),
        )
        if not span_payload and not full_document_payload:
            return _error_command(
                state=state,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                error_message=(
                    "Antes de proponer un patch debes leer un span focalizado con "
                    "read_document_span o el documento completo con read_document(mode='full')."
                ),
            )

        # Si el plan clínico requiere lectura completa (propagation/reinterpretation) y el planner
        # no la ejecutó, rechazar el propose para forzar la lectura completa primero.
        # Esto garantiza que el drafter tenga visibilidad de todas las secciones antes de
        # emitir patches multi-sección coherentes.
        clinical_plan = state.get("clinical_plan") or {}
        if clinical_plan.get("needs_full_note") and not full_document_payload:
            affected = ", ".join(clinical_plan.get("affected_sections") or []) or "varias"
            return _error_command(
                state=state,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                error_message=(
                    f"El plan clínico (edit_scope='{clinical_plan.get('edit_scope')}') "
                    f"requiere leer la nota completa antes de proponer patches en: {affected}. "
                    f"Usa read_document(document_id='{target_document_id}', mode='full') primero."
                ),
            )

        target_document_content = str(
            (full_document_payload or {}).get("content")
            or (span_payload or {}).get("content")
            or (summary_payload or {}).get("excerpt")
            or ""
        )

        try:
            drafted_plan = planner.draft_patch_preview(
                state=state,
                target_document=target_document,
                target_document_content=target_document_content,
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
    def set_edit_plan(
        edit_scope: str,
        clinical_impact_level: str,
        affected_sections: list[str],
        needs_full_note: bool,
        needs_external_knowledge: bool,
        should_propagate_to_analysis_and_plan: bool,
        runtime: ToolRuntime,
    ) -> Command:
        """Registra el plan de edición clínica ANTES de proponer patches.

        Llama esta tool cuando el pedido del médico implica un cambio de propagación clínica
        (nuevo dato que debe reflejarse en varias secciones) o reinterpretación clínica
        (el dato cambia análisis, impresión diagnóstica, riesgo o plan de manejo).

        NO es necesario para ediciones simples (typos, inserciones cortas, borrados puntuales).
        Para esos casos ve directamente a propose_*.

        Esta tool NO hace ninguna llamada externa. Solo escribe el plan al estado del runtime
        y eleva `max_patch_operations` según `edit_scope`:
          - local          → max 1 patch
          - propagation    → max 5 patches
          - reinterpretation → max 8 patches

        REGLAS de uso:
        - Llama set_edit_plan ANTES de propose_*, nunca en el mismo turno.
        - No llames set_edit_plan más de una vez por run.
        - Si needs_full_note=True, el runtime rechazará propose_* hasta que hagas
          read_document(mode='full') en el documento target.

        Valores válidos para edit_scope: 'local', 'propagation', 'reinterpretation'.
        Valores válidos para clinical_impact_level: 'cosmetic', 'factual', 'clinical'.
        affected_sections: lista snake_case, ej ['enfermedad_actual', 'plan'].
        """
        state, tool_call_id = _runtime_parts(runtime, tool_name="set_edit_plan")

        # Normalizar scope y calcular presupuesto de patches.
        # Un scope inválido se trata como 'local' para no bloquear el run.
        safe_scope = edit_scope if edit_scope in _MAX_PATCH_OPERATIONS_BY_SCOPE else "local"
        max_ops = _MAX_PATCH_OPERATIONS_BY_SCOPE[safe_scope]
        safe_impact = (
            clinical_impact_level
            if clinical_impact_level in ("cosmetic", "factual", "clinical")
            else "factual"
        )

        plan = {
            "edit_scope": safe_scope,
            "clinical_impact_level": safe_impact,
            "affected_sections": list(affected_sections or []),
            "needs_full_note": bool(needs_full_note),
            "needs_external_knowledge": bool(needs_external_knowledge),
            "should_propagate_to_analysis_and_plan": bool(should_propagate_to_analysis_and_plan),
        }
        payload = {**plan, "max_patch_operations": max_ops}

        return _success_command(
            state=state,
            tool_name="set_edit_plan",
            tool_call_id=tool_call_id,
            payload=payload,
            updates={
                # Escribir el plan al state para que render_patch_input lo inyecte
                # en el contexto del drafter en el siguiente turno de proposición.
                "clinical_plan": plan,
                # Levantar dinámicamente el presupuesto de patches según el alcance clínico.
                # Esto permite al drafter emitir un patch set coherente multi-sección en
                # una sola llamada LLM, en lugar de forzar múltiples turnos de propose_*.
                "max_patch_operations": max_ops,
            },
        )

    @tool
    def propose_replace_span(
        target_document_id: str,
        runtime: ToolRuntime,
    ) -> Command:
        """Draft a reviewable patch set centered on span replacement.

        Sequential precondition: You MUST NOT call this tool unless you have ALREADY called
        `read_document` para este documento target, y ademas `read_document_span` o
        `read_document(mode="full")` en PREVIOUS TURNS. Si intentas llamarla antes, fallara.
        Never call this in the same turn as read tools.
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

        Sequential precondition: You MUST NOT call this tool unless you have ALREADY called
        `read_document` para este documento target, y ademas `read_document_span` o
        `read_document(mode="full")` en PREVIOUS TURNS. Si intentas llamarla antes, fallara.
        Never call this in the same turn as read tools.
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
    def propose_insert_before(
        target_document_id: str,
        runtime: ToolRuntime,
    ) -> Command:
        """Draft a reviewable patch set centered on anchored insertion before a span.

        Sequential precondition: You MUST NOT call this tool unless you have ALREADY called
        `read_document` para este documento target, y ademas `read_document_span` o
        `read_document(mode="full")` en PREVIOUS TURNS. Si intentas llamarla antes, fallara.
        Never call this in the same turn as read tools.
        """
        state, tool_call_id = _runtime_parts(
            runtime,
            tool_name="propose_insert_before",
        )
        validated = ProposePatchInput(target_document_id=target_document_id)
        return _propose_patch(
            state=state,
            tool_call_id=tool_call_id,
            tool_name="propose_insert_before",
            target_document_id=validated.target_document_id,
        )

    @tool
    def propose_delete_span(
        target_document_id: str,
        runtime: ToolRuntime,
    ) -> Command:
        """Draft a reviewable patch set centered on deleting an anchored span.

        Sequential precondition: You MUST NOT call this tool unless you have ALREADY called
        `read_document` para este documento target, y ademas `read_document_span` o
        `read_document(mode="full")` en PREVIOUS TURNS. Si intentas llamarla antes, fallara.
        Never call this in the same turn as read tools.
        """
        state, tool_call_id = _runtime_parts(
            runtime,
            tool_name="propose_delete_span",
        )
        validated = ProposePatchInput(target_document_id=target_document_id)
        return _propose_patch(
            state=state,
            tool_call_id=tool_call_id,
            tool_name="propose_delete_span",
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
        read_document,
        read_document_summary,
        read_document_span,
        search_documents,
        read_patch_history,
        set_edit_plan,
        propose_replace_span,
        propose_insert_after_span,
        propose_insert_before,
        propose_delete_span,
        propose_create_document,
    ]
