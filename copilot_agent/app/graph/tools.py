from __future__ import annotations

import hashlib
import uuid
from typing import Any, Literal, Mapping, Protocol, Sequence
from xml.sax.saxutils import escape

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.types import Command
from pydantic import BaseModel, Field

try:  # pragma: no cover - import compatibility shim
    from langgraph.prebuilt import ToolRuntime
except ImportError:  # pragma: no cover - older langgraph in local test env
    ToolRuntime = Any

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
    mode: Literal["summary", "full"] = "full"


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
    # `instruction` fue agregado para resolver un bug donde el planner LLM intentaba
    # llamar propose_replace_span 5 veces en paralelo (una por cada reemplazo puntual),
    # y el filtro _filter_parallel_tool_calls descartaba 4 de ellas silenciosamente.
    # La raíz del problema: el planner no tenia forma de expresar QUE cambiar, solo
    # podía indicar EN QUE documento cambiar. Sin ese campo, el LLM alucinaba params
    # inexistentes (exact_text, new_text, current_text) para compensar.
    # Solución: un solo campo libre donde el planner consolida TODOS sus reemplazos
    # para ese documento, que el drafter LLM luego materializa en patches individuales.
    instruction: str | None = Field(
        default=None,
        description=(
            "Opcional pero muy recomendado. Describe EXACTAMENTE el texto que quieres buscar "
            "y como lo quieres reemplazar o estructurar. Si tienes varios cambios para este "
            "mismo documento target, consolidalos TODOS en un solo llamado a esta tool explicando "
            "cada cambio en esta instruction."
        )
    )
    affected_sections: list[str] | None = Field(
        default=None,
        description=(
            "Scope semantico opcional para edits locales directos a propose_*. "
            "Usa nombres de seccion snake_case cuando ya sabes exactamente donde debe aplicar "
            "el cambio (ej. ['analisis_clinico']). Activa el guardrail de scope aunque no "
            "hayas llamado set_edit_plan."
        ),
    )

class ProposeCreateDocumentInput(BaseModel):
    pass


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


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
            "content": fact["value"],
            "read_mode": "context_view",
        }
        for index, fact in enumerate((context_view or {}).get("facts") or [])
    ]
    document_items = [
        {
            "type": document.get("type", "document"),
            "document_id": document["document_id"],
            "title": document.get("title"),
            "content": _shorten_text(
                document.get("content") or "",
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
            "content": _shorten_text(span.get("content"), max_length=12000),
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
        if payload.get("reasoning"):
            lines.append(f"  {_xml_line('reasoning', payload.get('reasoning'))}")
        if payload.get("doctor_summary"):
            lines.append(f"  {_xml_line('doctor_summary', payload.get('doctor_summary'))}")
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
        modes=("summary", "full"),
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


def _fallback_target_document_id_from_state(state: CopilotState) -> str | None:
    explicit_target = str(state.get("target_document_id") or "").strip()
    if explicit_target:
        return explicit_target

    full_read_ids: list[str] = []
    seen_full_read_ids: set[str] = set()
    for document in state.get("read_documents") or []:
        read_mode = str(document.get("read_mode") or document.get("mode") or "")
        document_id = str(document.get("document_id") or "").strip()
        if read_mode != "full" or not document_id or document_id in seen_full_read_ids:
            continue
        seen_full_read_ids.add(document_id)
        full_read_ids.append(document_id)
    if len(full_read_ids) == 1:
        return full_read_ids[0]

    read_ids: list[str] = []
    seen_read_ids: set[str] = set()
    for document in state.get("read_documents") or []:
        document_id = str(document.get("document_id") or "").strip()
        if not document_id or document_id in seen_read_ids:
            continue
        seen_read_ids.add(document_id)
        read_ids.append(document_id)
    if len(read_ids) == 1:
        return read_ids[0]

    selected_ids = _default_selected_document_ids(state)
    if len(selected_ids) == 1:
        return selected_ids[0]
    return None


def _has_full_read_for_document(state: CopilotState, *, document_id: str) -> bool:
    return _current_document_read(
        state,
        document_id=document_id,
        modes=("full",),
    ) is not None


def _normalize_affected_sections(affected_sections: Sequence[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for section in affected_sections or []:
        value = str(section or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _build_runtime_instruction(
    *,
    state: Mapping[str, Any],
    affected_sections: Sequence[str] | None = None,
) -> str:
    user_query = str(state.get("user_message") or "").strip()
    clinical_plan = state.get("clinical_plan") or {}
    sections = _normalize_affected_sections(
        affected_sections if affected_sections is not None else clinical_plan.get("affected_sections")
    )
    reasoning = str(clinical_plan.get("reasoning") or "").strip()
    section_instructions = clinical_plan.get("section_instructions") or {}

    parts: list[str] = []
    if user_query:
        parts.append(f"Pedido actual del medico: {user_query}.")
    if sections:
        parts.append(
            "Aplica el cambio solo dentro de estas secciones: "
            + ", ".join(sections)
            + "."
        )
    if reasoning:
        parts.append(f"Contexto clinico heredado: {reasoning}.")
    if section_instructions:
        scoped_instructions: list[str] = []
        for section_name, section_instruction in section_instructions.items():
            if sections and str(section_name) not in sections:
                continue
            scoped_instructions.append(
                f"{section_name}: {str(section_instruction).strip()}"
            )
        if scoped_instructions:
            parts.append(
                "Instrucciones quirurgicas por seccion: "
                + " | ".join(scoped_instructions)
                + "."
            )
    if sections:
        parts.append("No toques otras secciones del documento aunque contengan texto parecido.")
    return " ".join(part for part in parts if part).strip() or (
        user_query or "Materializa el cambio pedido usando el documento leido."
    )


def _effective_scope_plan(
    *,
    state: CopilotState,
    affected_sections: Sequence[str] | None = None,
) -> dict[str, Any]:
    clinical_plan = dict(state.get("clinical_plan") or {})
    if clinical_plan:
        if affected_sections:
            clinical_plan["affected_sections"] = _normalize_affected_sections(affected_sections)
        return clinical_plan

    normalized_sections = _normalize_affected_sections(affected_sections)
    if not normalized_sections:
        return {}

    return {
        "edit_scope": "local",
        "clinical_impact_level": "factual",
        "affected_sections": normalized_sections,
        "needs_full_note": False,
        "needs_external_knowledge": False,
        "reasoning": None,
        "doctor_summary": None,
        "section_instructions": None,
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


def _normalize_section_name(value: Any) -> str:
    return str(value or "").strip().lower()


def _patch_content_preview(patch: Any) -> str:
    operation_type = str(getattr(patch, "operation_type", "") or "")
    if operation_type in {"replace_span", "rewrite_document"}:
        return str(getattr(patch, "replacement_text", "") or "")
    if operation_type in {"insert_before", "insert_after_span"}:
        return str(getattr(patch, "inserted_text", "") or "")
    return str(getattr(patch, "content_preview", "") or "")


def _validate_drafted_plan_against_clinical_plan(
    *,
    drafted_plan: DraftedPatchPlan,
    clinical_plan: Mapping[str, Any],
) -> str | None:
    edit_scope = _normalize_section_name(clinical_plan.get("edit_scope"))

    expected_sections: list[str] = []
    seen_expected: set[str] = set()
    for section in clinical_plan.get("affected_sections") or []:
        normalized = _normalize_section_name(section)
        if not normalized or normalized in seen_expected:
            continue
        seen_expected.add(normalized)
        expected_sections.append(normalized)

    if not expected_sections:
        return None

    # Fail closed whenever the planner declared explicit semantic scope via
    # affected_sections, even for edit_scope='local'. Without this guard the
    # drafter may silently spill into adjacent sections or return only a partial
    # subset of the intended scoped edit while still opening review as if it
    # matched planner intent.
    patch_sections: set[str] = set()
    patches_without_section: list[int] = []
    invalid_sections: set[str] = set()
    for index, patch in enumerate(drafted_plan.patches, start=1):
        normalized_section = _normalize_section_name(patch.section)
        if not normalized_section:
            patches_without_section.append(index)
            continue
        if normalized_section not in seen_expected:
            invalid_sections.add(normalized_section)
            continue
        patch_sections.add(normalized_section)

    missing_sections = [
        section for section in expected_sections if section not in patch_sections
    ]
    if not patches_without_section and not invalid_sections and not missing_sections:
        return None

    issues: list[str] = []
    if patches_without_section:
        issues.append(
            "patches sin section en posiciones: "
            + ", ".join(str(index) for index in patches_without_section)
            + "."
        )
    if invalid_sections:
        issues.append(
            "sections fuera del plan clínico: "
            + ", ".join(sorted(invalid_sections))
            + "."
        )
    if missing_sections:
        issues.append(
            "faltan secciones obligatorias: "
            + ", ".join(missing_sections)
            + "."
        )

    return (
        "El drafter devolvió un patch set fuera del scope declarado por el planner. "
        f"Scope={edit_scope or 'local'}. Se esperaban patches para: {', '.join(expected_sections)}. "
        + " ".join(issues)
        + " Regenera el patch set completo y asigna section a cada patch antes de abrir review."
    )


def _build_patch_set_preview_payload(
    *,
    state: CopilotState,
    drafted_plan: DraftedPatchPlan,
    target_document: dict[str, Any],
    summary_payload: dict[str, Any],
    span_payload: dict[str, Any] | None,
    scope_plan: Mapping[str, Any] | None,
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
        content_preview = _patch_content_preview(patch)
        document_preview_after = (
            drafted_plan.document_preview_after
            or content_preview
        )
        patches.append(
            {
                "patch_id": str(uuid.uuid4()),
                "patch_type": patch.operation_type,
                "operation_type": patch.operation_type,
                "order_index": index,
                "anchor": patch.anchor.to_payload(),
                "expected_hash": patch.expected_hash,
                "replacement_text": patch.replacement_text,
                "inserted_text": patch.inserted_text,
                "old_text": None,
                "new_text": None,
                "document_preview_after": document_preview_after,
                "content_preview": content_preview,
                "rationale": patch.rationale,
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
    clinical_plan = dict(scope_plan or {})
    base_hash = (
        summary_payload.get("content_hash")
        or (span_payload or {}).get("content_hash")
    )
    if not base_hash and str(summary_payload.get("mode") or "") == "full":
        full_content = summary_payload.get("content")
        if isinstance(full_content, str) and full_content:
            base_hash = _content_hash(full_content)

    return {
        "patch_set_id": str(uuid.uuid4()),
        "target_document_id": target_document_id,
        "target_document_title": target_document_title,
        "target_selection_reason": selection_reason,
        "base_version": base_version,
        "base_hash": base_hash,
        "rationale": drafted_plan.rationale,
        "document_preview_after": drafted_plan.document_preview_after,
        "source_context_document_ids": source_context_document_ids,
        "edit_scope": clinical_plan.get("edit_scope"),
        "clinical_impact_level": clinical_plan.get("clinical_impact_level"),
        "affected_sections": list(clinical_plan.get("affected_sections") or []),
        "patches": patches,
    }


def draft_patch_set_from_state(
    *,
    planner: CopilotPlanner,
    state: CopilotState,
    tool_name: str,
    target_document_id: str,
    instruction: str | None = None,
    affected_sections: Sequence[str] | None = None,
) -> dict[str, Any]:
    effective_scope_plan = _effective_scope_plan(
        state=state,
        affected_sections=affected_sections,
    )
    requested_instruction = (instruction or "").strip() or _build_runtime_instruction(
        state=state,
        affected_sections=effective_scope_plan.get("affected_sections"),
    )

    if int(state.get("patch_operations_count") or 0) >= int(
        state.get("max_patch_operations") or 1
    ):
        return {
            "ok": False,
            "error_message": "El run ya consumio el presupuesto maximo de operaciones de patch.",
            "updates": {
                "next_required_action": None,
                "planned_target_document_id": None,
                "last_tool_error": "El run ya consumio el presupuesto maximo de operaciones de patch.",
            },
        }

    target_document = _find_document(state, document_id=target_document_id)
    if not target_document:
        error_message = (
            f"El documento target {target_document_id} no existe en el workspace actual."
        )
        return {
            "ok": False,
            "error_message": error_message,
            "updates": {
                "next_required_action": None,
                "planned_target_document_id": None,
                "last_tool_error": error_message,
            },
        }
    if target_document.get("ai_writable") is False:
        error_message = (
            f"El documento target {target_document_id} no es editable por el copiloto."
        )
        return {
            "ok": False,
            "error_message": error_message,
            "updates": {
                "next_required_action": None,
                "planned_target_document_id": None,
                "last_tool_error": error_message,
            },
        }

    summary_payload = _current_summary(state, document_id=target_document_id) or _current_document_read(
        state,
        document_id=target_document_id,
        modes=("summary", "full"),
    )
    if not summary_payload:
        error_message = (
            "Antes de proponer un patch debes leer el documento target con "
            "read_document(mode='summary'|'full')."
        )
        return {
            "ok": False,
            "error_message": error_message,
            "updates": {
                "next_required_action": None,
                "planned_target_document_id": None,
                "last_tool_error": error_message,
            },
        }

    span_payload = _current_span(state, document_id=target_document_id)
    full_document_payload = _current_document_read(
        state,
        document_id=target_document_id,
        modes=("full",),
    )
    if not span_payload and not full_document_payload:
        error_message = (
            "Antes de proponer un patch debes leer un span focalizado con "
            "read_document_span o el documento completo con read_document(mode='full')."
        )
        return {
            "ok": False,
            "error_message": error_message,
            "updates": {
                "next_required_action": None,
                "planned_target_document_id": None,
                "last_tool_error": error_message,
            },
        }

    if effective_scope_plan.get("needs_full_note") and not full_document_payload:
        affected = ", ".join(effective_scope_plan.get("affected_sections") or []) or "varias"
        error_message = (
            f"El plan clínico (edit_scope='{effective_scope_plan.get('edit_scope')}') "
            f"requiere leer la nota completa antes de proponer patches en: {affected}. "
            f"Usa read_document(document_id='{target_document_id}', mode='full') primero."
        )
        return {
            "ok": False,
            "error_message": error_message,
            "updates": {
                "last_tool_error": error_message,
            },
        }

    target_document_content = str(
        (full_document_payload or {}).get("content")
        or (span_payload or {}).get("content")
        or (summary_payload or {}).get("excerpt")
        or ""
    )

    try:
        drafted_plan = planner.draft_patch_preview(
            state={**state, "clinical_plan": effective_scope_plan or state.get("clinical_plan")},
            target_document=target_document,
            target_document_content=target_document_content,
            supporting_context=_build_retrieved_context(
                context_view=state.get("context_view"),
                read_documents=state.get("read_documents") or [],
                read_spans=state.get("read_spans") or [],
            ),
            span_payload=span_payload,
            requested_tool_name=tool_name,
            requested_tool_instruction=requested_instruction,
            requested_affected_sections=list(effective_scope_plan.get("affected_sections") or []),
        )
    except Exception as error:
        error_str = str(error)
        is_resource_exhausted = "RESOURCE_EXHAUSTED" in error_str or "429" in error_str
        if is_resource_exhausted:
            return {
                "ok": False,
                "error_message": "RECURSO DE IA AGOTADO (429). No reintentes este patch en este run.",
                "updates": {
                    "run_error": "Recurso de IA agotado (429)",
                    "final_response": (
                        "En este momento hay una demanda muy alta en el servicio de IA "
                        "y no pude completar la edición. "
                        "Por favor, inténtalo de nuevo en unos minutos."
                    ),
                    "last_tool_error": "Recurso de IA agotado (429)",
                    "next_required_action": None,
                    "planned_target_document_id": None,
                },
            }
        error_message = f"No pude redactar un patch clinico seguro: {error}"
        return {
            "ok": False,
            "error_message": error_message,
            "updates": {
                "last_tool_error": error_message,
                "next_required_action": None,
                "planned_target_document_id": None,
            },
        }

    if not drafted_plan.patches:
        error_message = (
            "No se pudo redactar un patch clinico revisable para esta solicitud. "
            "El LLM no devolvio cambios materializados."
        )
        return {
            "ok": False,
            "error_message": error_message,
            "updates": {
                "last_tool_error": error_message,
                "next_required_action": None,
                "planned_target_document_id": None,
            },
        }

    drafted_plan_validation_error = _validate_drafted_plan_against_clinical_plan(
        drafted_plan=drafted_plan,
        clinical_plan=effective_scope_plan,
    )
    if drafted_plan_validation_error:
        return {
            "ok": False,
            "error_message": drafted_plan_validation_error,
            "updates": {
                "last_tool_error": drafted_plan_validation_error,
                "next_required_action": None,
                "planned_target_document_id": None,
            },
        }

    payload = _build_patch_set_preview_payload(
        state=state,
        drafted_plan=drafted_plan,
        target_document=target_document,
        summary_payload=summary_payload,
        span_payload=span_payload,
        scope_plan=effective_scope_plan,
    )
    if not _is_valid_patch_set_preview(payload):
        error_message = (
            "El runtime no pudo construir un patch set revisable con metadata completa."
        )
        return {
            "ok": False,
            "error_message": error_message,
            "updates": {
                "last_tool_error": error_message,
                "next_required_action": None,
                "planned_target_document_id": None,
            },
        }

    first_patch = payload["patches"][0]
    return {
        "ok": True,
        "payload": payload,
        "updates": {
            "target_document_id": payload["target_document_id"],
            "target_document_title": payload["target_document_title"],
            "target_selection_reason": payload["target_selection_reason"],
            "base_version": payload["base_version"],
            "patch_set_preview": payload,
            "patch_preview": first_patch,
            "patch_id": first_patch["patch_id"],
            "requires_human_review": True,
            "final_response": None,
            "last_tool_error": None,
            "next_required_action": None,
            "planned_target_document_id": None,
            "patch_operations_count": int(state.get("patch_operations_count") or 0) + 1,
        },
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
        mode: Literal["summary", "full"] = "full",
    ) -> Command:
        """
        Lee un documento completo o un resumen segun la necesidad.
        Usa `mode="summary"` para orientarte rapido (solo metadatos + excerpt corto).
        Usa `mode="full"` cuando necesites el texto completo para proponer patches,
        verificar estructura global o insertar al inicio/final del documento.
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
        """Lee un fragmento focalizado de un documento.

        Usa este tool cuando ya sabes QUÉ sección necesitas leer pero no su contenido exacto.
        No lo uses como sustituto de read_document(mode='full') para ediciones multi-sección.

        Hay dos formas de anclar el span:

        1. `exact_text` (recomendado para spans puntuales): proporciona una frase CORTA Y ÚNICA
           (3-8 palabras) de una sola línea del documento. El backend la busca como substring
           exacto. No incluyas saltos de línea (\\n) ni párrafos largos.
           Opcionalmente añade `prefix_text` / `suffix_text` para desambiguar si el texto
           aparece más de una vez. Devuelve exactamente ese fragmento + max_chars alrededor.

        2. `prefix_text` SOLO, SIN exact_text (para leer una sección entera por su encabezado):
           proporciona el encabezado EXACTO de la sección como aparece en el documento,
           por ejemplo `"## 10. Plan de manejo"`.
           El backend lo localiza y devuelve desde ahí hasta el siguiente encabezado (#/##)
           o hasta max_chars, lo que ocurra primero.
           Úsalo cuando sabes el título de la sección pero no su contenido.
           NO funciona si el encabezado aparece más de una vez en el documento.

        NUNCA uses este tool para leer una sección si ya tienes el documento completo en
        contexto (de un read_document previo en modo full). En ese caso el contenido ya está
        disponible y una segunda lectura parcial no aporta nada al drafter.
        """
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

    @tool
    def set_edit_plan(
        edit_scope: str,
        clinical_impact_level: str,
        affected_sections: list[str],
        needs_full_note: bool,
        needs_external_knowledge: bool,
        runtime: ToolRuntime,
        reasoning: str | None = None,
        doctor_summary: str | None = None,
        section_instructions: dict[str, str] | None = None,
    ) -> Command:
        """Registra el plan de edición clínica y transfiere el run al drafting runtime.

        Llama esta tool cuando el pedido del médico implica un cambio de propagación clínica
        (nuevo dato que debe reflejarse en varias secciones) o reinterpretación clínica
        (el dato cambia análisis, impresión diagnóstica, riesgo o plan de manejo).

        NO es necesario para ediciones simples (typos, inserciones cortas, borrados puntuales).
        Para esos casos ve directamente a propose_*.

        Esta tool NO redacta patches por sí sola. Solo escribe el plan al estado del runtime,
        fija el siguiente paso requerido (`draft_patch_set`) y eleva `max_patch_operations`
        según `edit_scope`:
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
        OJO: 'cosmetic' describe impacto semántico, no tamaño del cambio. Un reformateo
        amplio puede requerir propagation si toca varias secciones aunque no cambie datos.
        affected_sections: lista snake_case, ej ['enfermedad_actual', 'plan'].
        reasoning: razonamiento clínico interno que explica POR QUÉ ese scope y esas secciones.
          Llega al drafter para guiar la redacción. Para ediciones locales puede omitirse.
        doctor_summary: mensaje en lenguaje natural dirigido al médico explicando qué se va
          a cambiar y por qué. Se muestra en el chat mientras el drafter genera los patches.
          Escríbelo en primera persona, breve y claro.
          Ejemplo: 'Voy a corregir el diagnóstico de diabetes en antecedentes, plan y análisis
          clínico, ya que fue descartado en la consulta de hoy.'
        section_instructions: instrucciones quirúrgicas por sección para el drafter.
          Claves = nombres de sección (snake_case), valores = qué cambiar exactamente.
          Ejemplo: {{
            'antecedentes_relevantes': 'Eliminar Diabetes mellitus tipo 2 de la lista de antecedentes',
            'plan': 'Remover control glucémico y HbA1c del esquema terapéutico',
            'analisis_clinico': 'Corregir el párrafo que trata la diabetes como condición activa'
          }}
          Proporciona section_instructions para propagation y reinterpretation siempre que
          puedas. El drafter las prioriza sobre inferir el cambio desde reasoning o user_query.
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

        safe_section_instructions: dict[str, str] | None = None
        if section_instructions and isinstance(section_instructions, dict):
            # Solo conservar entradas cuya clave coincida con affected_sections para
            # evitar que el planner inyecte instrucciones para secciones no declaradas.
            allowed = set(affected_sections or [])
            safe_section_instructions = {
                k: str(v)
                for k, v in section_instructions.items()
                if isinstance(k, str) and isinstance(v, str) and (not allowed or k in allowed)
            } or None

        plan = {
            "edit_scope": safe_scope,
            "clinical_impact_level": safe_impact,
            "affected_sections": list(affected_sections or []),
            "needs_full_note": bool(needs_full_note),
            "needs_external_knowledge": bool(needs_external_knowledge),
            # reasoning: razonamiento interno para el drafter.
            # doctor_summary: mensaje en lenguaje natural para el médico visible en el chat.
            # section_instructions: instrucciones quirúrgicas por sección para el drafter.
            "reasoning": (reasoning or "").strip() or None,
            "doctor_summary": (doctor_summary or "").strip() or None,
            "section_instructions": safe_section_instructions,
        }
        payload = {**plan, "max_patch_operations": max_ops}

        planned_target_document_id = _fallback_target_document_id_from_state(state)

        return _success_command(
            state=state,
            tool_name="set_edit_plan",
            tool_call_id=tool_call_id,
            payload=payload,
            updates={
                # Escribir el plan al state para que el runtime pueda saltar
                # directamente a drafting sin otra decisión abierta del planner.
                "clinical_plan": plan,
                "max_patch_operations": max_ops,
                "next_required_action": "draft_patch_set",
                "planned_target_document_id": planned_target_document_id,
            },
        )

    @tool
    def propose_replace_span(
        target_document_id: str,
        runtime: ToolRuntime,
        instruction: str | None = None,
        affected_sections: list[str] | None = None,
    ) -> Command:
        """Draft a reviewable patch set centered on span replacement.

        Sequential precondition: el documento target debe aparecer en `<read_documents>` del
        contexto con mode='full'. Esto se cumple automaticamente si el documento es editable
        (ai_writable=true) porque se pre-carga al inicio de cada run — en ese caso NO necesitas
        llamar read_document antes de propose_*. Solo llama read_document si el documento NO
        aparece aun en <read_documents> con mode='full'. Nunca combinas read tools y propose_*
        en el mismo turno.
        
        Optional 'instruction': Describe exactamente QUE texto quieres localizar y por QUE 
        nuevo texto reemplazarlo. Si tienes multiples reemplazos para este documento localizados,
        juntalos todos en UNA sola llamada a esta tool, detallandolos en instruction.
        Optional 'affected_sections': usa una o mas secciones snake_case cuando el scope local
        ya es conocido y quieres activar el guardrail semantico sin pasar por set_edit_plan.
        """
        state, tool_call_id = _runtime_parts(
            runtime,
            tool_name="propose_replace_span",
        )
        validated = ProposePatchInput(
            target_document_id=target_document_id,
            instruction=instruction,
            affected_sections=affected_sections,
        )
        result = draft_patch_set_from_state(
            planner=planner,
            state=state,
            tool_name="propose_replace_span",
            target_document_id=validated.target_document_id,
            instruction=validated.instruction,
            affected_sections=validated.affected_sections,
        )
        if not result["ok"]:
            return _error_command(
                state=state,
                tool_name="propose_replace_span",
                tool_call_id=tool_call_id,
                error_message=result["error_message"],
                updates=result.get("updates"),
            )
        return _success_command(
            state=state,
            tool_name="propose_replace_span",
            tool_call_id=tool_call_id,
            payload=result["payload"],
            updates=result["updates"],
        )

    @tool
    def propose_insert_after_span(
        target_document_id: str,
        runtime: ToolRuntime,
        instruction: str | None = None,
        affected_sections: list[str] | None = None,
    ) -> Command:
        """Draft a reviewable patch set centered on anchored insertion.

        Sequential precondition: el documento target debe aparecer en `<read_documents>` del
        contexto con mode='full'. Esto se cumple automaticamente si el documento es editable
        (ai_writable=true) porque se pre-carga al inicio de cada run — en ese caso NO necesitas
        llamar read_document antes de propose_*. Solo llama read_document si el documento NO
        aparece aun en <read_documents> con mode='full'. Nunca combinas read tools y propose_*
        en el mismo turno.
        
        Optional 'instruction': Describe exactly WHAT text to insert and WHERE (after which span).
        If you have multiple insertions for this document, consolidate them into ONE tool call
        and detail all of them in instruction.
        Optional 'affected_sections': usa una o mas secciones snake_case cuando el scope local
        ya es conocido y quieres activar el guardrail semantico sin pasar por set_edit_plan.
        """
        state, tool_call_id = _runtime_parts(
            runtime,
            tool_name="propose_insert_after_span",
        )
        validated = ProposePatchInput(
            target_document_id=target_document_id,
            instruction=instruction,
            affected_sections=affected_sections,
        )
        result = draft_patch_set_from_state(
            planner=planner,
            state=state,
            tool_name="propose_insert_after_span",
            target_document_id=validated.target_document_id,
            instruction=validated.instruction,
            affected_sections=validated.affected_sections,
        )
        if not result["ok"]:
            return _error_command(
                state=state,
                tool_name="propose_insert_after_span",
                tool_call_id=tool_call_id,
                error_message=result["error_message"],
                updates=result.get("updates"),
            )
        return _success_command(
            state=state,
            tool_name="propose_insert_after_span",
            tool_call_id=tool_call_id,
            payload=result["payload"],
            updates=result["updates"],
        )

    @tool
    def propose_insert_before(
        target_document_id: str,
        runtime: ToolRuntime,
        instruction: str | None = None,
        affected_sections: list[str] | None = None,
    ) -> Command:
        """Draft a reviewable patch set centered on anchored insertion before a span.

        Sequential precondition: el documento target debe aparecer en `<read_documents>` del
        contexto con mode='full'. Esto se cumple automaticamente si el documento es editable
        (ai_writable=true) porque se pre-carga al inicio de cada run — en ese caso NO necesitas
        llamar read_document antes de propose_*. Solo llama read_document si el documento NO
        aparece aun en <read_documents> con mode='full'. Nunca combinas read tools y propose_*
        en el mismo turno.
        
        Optional 'instruction': Describe exactly WHAT text to insert and WHERE (before which span).
        If you have multiple insertions for this document, consolidate them into ONE tool call
        and detail all of them in instruction.
        Optional 'affected_sections': usa una o mas secciones snake_case cuando el scope local
        ya es conocido y quieres activar el guardrail semantico sin pasar por set_edit_plan.
        """
        state, tool_call_id = _runtime_parts(
            runtime,
            tool_name="propose_insert_before",
        )
        validated = ProposePatchInput(
            target_document_id=target_document_id,
            instruction=instruction,
            affected_sections=affected_sections,
        )
        result = draft_patch_set_from_state(
            planner=planner,
            state=state,
            tool_name="propose_insert_before",
            target_document_id=validated.target_document_id,
            instruction=validated.instruction,
            affected_sections=validated.affected_sections,
        )
        if not result["ok"]:
            return _error_command(
                state=state,
                tool_name="propose_insert_before",
                tool_call_id=tool_call_id,
                error_message=result["error_message"],
                updates=result.get("updates"),
            )
        return _success_command(
            state=state,
            tool_name="propose_insert_before",
            tool_call_id=tool_call_id,
            payload=result["payload"],
            updates=result["updates"],
        )

    @tool
    def propose_delete_span(
        target_document_id: str,
        runtime: ToolRuntime,
        instruction: str | None = None,
        affected_sections: list[str] | None = None,
    ) -> Command:
        """Draft a reviewable patch set centered on deleting an anchored span.

        Sequential precondition: el documento target debe aparecer en `<read_documents>` del
        contexto con mode='full'. Esto se cumple automaticamente si el documento es editable
        (ai_writable=true) porque se pre-carga al inicio de cada run — en ese caso NO necesitas
        llamar read_document antes de propose_*. Solo llama read_document si el documento NO
        aparece aun en <read_documents> con mode='full'. Nunca combinas read tools y propose_*
        en el mismo turno.
        
        Optional 'instruction': Describe exactly WHICH text to delete.
        If you have multiple deletions for this document, consolidate them into ONE tool call
        and detail all of them in instruction.
        Optional 'affected_sections': usa una o mas secciones snake_case cuando el scope local
        ya es conocido y quieres activar el guardrail semantico sin pasar por set_edit_plan.
        """
        state, tool_call_id = _runtime_parts(
            runtime,
            tool_name="propose_delete_span",
        )
        validated = ProposePatchInput(
            target_document_id=target_document_id,
            instruction=instruction,
            affected_sections=affected_sections,
        )
        result = draft_patch_set_from_state(
            planner=planner,
            state=state,
            tool_name="propose_delete_span",
            target_document_id=validated.target_document_id,
            instruction=validated.instruction,
            affected_sections=validated.affected_sections,
        )
        if not result["ok"]:
            return _error_command(
                state=state,
                tool_name="propose_delete_span",
                tool_call_id=tool_call_id,
                error_message=result["error_message"],
                updates=result.get("updates"),
            )
        return _success_command(
            state=state,
            tool_name="propose_delete_span",
            tool_call_id=tool_call_id,
            payload=result["payload"],
            updates=result["updates"],
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
