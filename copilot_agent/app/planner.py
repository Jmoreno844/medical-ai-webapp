from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Protocol

import vertexai
from pydantic import BaseModel, Field, ValidationError
from vertexai.generative_models import GenerationConfig, GenerativeModel

from app.config import Settings

logger = logging.getLogger(__name__)

ALLOWED_TOOL_NAMES = {
    "list_open_documents",
    "list_encounter_documents",
    "read_document_summary",
    "read_document_span",
    "search_documents",
    "read_patch_history",
    "build_context_view",
    "propose_replace_span",
    "propose_insert_after_span",
    "propose_create_document",
}

EDIT_KEYWORDS = {
    "edita",
    "actualiza",
    "reescribe",
    "cambia",
    "corrige",
    "agrega",
    "agregale",
    "incluye",
    "pon",
    "modifica",
    "anade",
    "añade",
}

EDIT_PHRASES = {
    "haz el egreso",
    "haz la nota",
    "haz nota",
    "prepara el egreso",
    "prepara la nota",
    "completa el egreso",
}

DOCUMENT_TITLE_FAMILIES = {
    "clinical_note": {"nota", "nota clinica", "historia clinica", "soap", "evolucion"},
    "discharge_note": {"egreso", "epicrisis", "discharge"},
    "transcription": {"transcripcion", "transcript"},
    "context": {"contexto"},
}

EDIT_INTENT_HINTS = {
    "edit",
    "document",
    "patch",
    "rewrite",
    "replace",
    "insert",
    "add_information",
    "update",
    "modify",
}

TOOL_ALLOWED_INPUT_KEYS = {
    "list_open_documents": set(),
    "list_encounter_documents": set(),
    "read_document_summary": {"document_id"},
    "read_document_span": {
        "document_id",
        "exact_text",
        "prefix_text",
        "suffix_text",
        "start_offset",
        "end_offset",
        "max_chars",
    },
    "search_documents": {"query", "max_results", "allowed_document_types"},
    "read_patch_history": {"document_id", "limit"},
    "build_context_view": {
        "active_document_id",
        "include_document_ids",
        "include_manual_context",
    },
    "propose_replace_span": {"target_document_id"},
    "propose_insert_after_span": {"target_document_id"},
    "propose_create_document": set(),
}

TOOL_INPUT_ALIASES = {
    "build_context_view": {"document_id": "active_document_id"},
    "read_document_span": {
        "exactText": "exact_text",
        "prefixText": "prefix_text",
        "suffixText": "suffix_text",
        "startOffset": "start_offset",
        "endOffset": "end_offset",
        "documentId": "document_id",
    },
    "search_documents": {
        "topK": "max_results",
        "allowedDocumentTypes": "allowed_document_types",
    },
    "read_document_summary": {"documentId": "document_id"},
    "read_patch_history": {"documentId": "document_id"},
    "propose_replace_span": {"targetDocumentId": "target_document_id"},
    "propose_insert_after_span": {"targetDocumentId": "target_document_id"},
}


class PlannerDecision(BaseModel):
    action_type: str
    tool_name: str | None = None
    tool_input: dict[str, Any] = Field(default_factory=dict)
    reasoning_summary: str = ""
    response_content: str | None = None
    intent: str | None = None
    target_document_hint: str | None = None


class DraftedPatch(BaseModel):
    operation_type: str
    anchor: dict[str, Any] = Field(default_factory=dict)
    expected_hash: str | None = None
    before_preview: str | None = None
    after_preview: str | None = None
    document_preview_after: str
    content_preview: str
    rationale: str


class CopilotPlanner(Protocol):
    def plan_next_action(self, state: dict[str, Any]) -> PlannerDecision: ...

    def draft_patch_preview(
        self,
        *,
        state: dict[str, Any],
        target_document: dict[str, Any],
        target_document_content: str,
        supporting_context: list[dict[str, Any]],
        span_payload: dict[str, Any] | None = None,
    ) -> DraftedPatch: ...


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _extract_json_object(value: str) -> str:
    start = value.find("{")
    end = value.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Planner response did not contain a JSON object")
    return value[start : end + 1]


def _shorten_text(value: str | None, max_length: int = 240) -> str:
    if not value:
        return ""
    return " ".join(value.split())[:max_length]


def _is_simple_greeting(message: str) -> bool:
    normalized = _normalize_text(message.lower()).strip()
    return normalized in {"hola", "buenas", "hello", "hi", "buen dia", "buenas tardes"}


def _message_mentions_edit(message: str) -> bool:
    normalized_message = _normalize_text(message.lower())
    return any(keyword in normalized_message for keyword in EDIT_KEYWORDS) or any(
        phrase in normalized_message for phrase in EDIT_PHRASES
    )


def _message_document_hint(message: str) -> str | None:
    normalized_message = _normalize_text(message.lower())
    for family_alias in DOCUMENT_TITLE_FAMILIES["clinical_note"]:
        if family_alias in normalized_message:
            return "nota"
    for family_alias in DOCUMENT_TITLE_FAMILIES["discharge_note"]:
        if family_alias in normalized_message:
            return "egreso"
    return None


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _canonical_intent(
    *,
    raw_intent: str | None,
    action_type: str,
    tool_name: str | None,
    user_message: str,
) -> str:
    normalized_intent = _normalize_text((raw_intent or "").lower())
    if any(hint in normalized_intent for hint in EDIT_INTENT_HINTS):
        return "edit_document"
    if tool_name and tool_name.startswith("propose_"):
        return "edit_document"
    if _message_mentions_edit(user_message):
        return "edit_document"
    if action_type == "respond":
        return "answer_question"
    return "answer_question"


def _sanitize_tool_input(tool_name: str, raw_tool_input: Any) -> dict[str, Any]:
    if not isinstance(raw_tool_input, dict):
        raw_tool_input = {}

    aliases = TOOL_INPUT_ALIASES.get(tool_name, {})
    normalized_input: dict[str, Any] = {}
    for raw_key, raw_value in raw_tool_input.items():
        target_key = aliases.get(raw_key, raw_key)
        normalized_input[target_key] = raw_value

    allowed_keys = TOOL_ALLOWED_INPUT_KEYS[tool_name]
    sanitized_input = {
        key: value for key, value in normalized_input.items() if key in allowed_keys
    }

    if tool_name == "build_context_view":
        include_document_ids = sanitized_input.get("include_document_ids")
        if isinstance(include_document_ids, str):
            sanitized_input["include_document_ids"] = [include_document_ids]
        if "include_manual_context" in sanitized_input:
            sanitized_input["include_manual_context"] = bool(
                sanitized_input["include_manual_context"]
            )
    if tool_name == "search_documents" and "max_results" in sanitized_input:
        sanitized_input["max_results"] = int(sanitized_input["max_results"])
    if tool_name == "read_document_span" and "max_chars" in sanitized_input:
        sanitized_input["max_chars"] = int(sanitized_input["max_chars"])
    if tool_name == "read_patch_history" and "limit" in sanitized_input:
        sanitized_input["limit"] = int(sanitized_input["limit"])

    if tool_name in {"read_document_summary", "read_document_span", "read_patch_history"}:
        if not sanitized_input.get("document_id"):
            raise ValueError(f"{tool_name} requires document_id")
    if tool_name in {"propose_replace_span", "propose_insert_after_span"}:
        if not sanitized_input.get("target_document_id"):
            raise ValueError(f"{tool_name} requires target_document_id")

    return sanitized_input


def _best_target_document(
    state: dict[str, Any],
    *,
    preferred_hint: str | None = None,
) -> dict[str, Any] | None:
    documents = state.get("available_documents") or []
    writable_documents = [
        document
        for document in documents
        if document.get("ai_writable", True) and document.get("type") != "transcription"
    ]
    if not writable_documents:
        return None

    normalized_hint = _normalize_text((preferred_hint or "").lower())
    active_document_id = str(state.get("active_document_id") or "")

    def score(document: dict[str, Any]) -> int:
        result = 0
        title = _normalize_text(str(document.get("title") or "").lower())
        doc_type = _normalize_text(str(document.get("type") or "").lower())
        if normalized_hint and normalized_hint in title:
            result += 100
        if str(document.get("document_id")) == active_document_id:
            result += 20
        if doc_type == "note":
            result += 12
        if "nota" in title or "historia" in title:
            result += 30
        if "egreso" in title or "epicrisis" in title:
            result += 28
        if doc_type == "context":
            result -= 30
        return result

    return max(writable_documents, key=score)


def _extract_requested_addition(user_message: str) -> str | None:
    date_match = re.search(
        r"fecha(?: de hoy)?(?: es)?\s+(?P<date>.+)$",
        user_message,
        flags=re.IGNORECASE,
    )
    if date_match:
        return f"Fecha: {date_match.group('date').strip(' .,:;')}"

    content_match = re.search(
        r"(?:agregale|agrega|incluye|pon|anade|añade)\s+(?P<content>.+)$",
        user_message,
        flags=re.IGNORECASE,
    )
    if not content_match:
        return None
    return content_match.group("content").strip(" .,:;")


def _choose_anchor_span(content: str) -> tuple[int, int]:
    paragraphs = [segment for segment in content.split("\n\n") if segment.strip()]
    if paragraphs:
        first_paragraph = paragraphs[0]
        start = content.find(first_paragraph)
        if start >= 0:
            return start, start + len(first_paragraph)

    lines = [segment for segment in content.splitlines() if segment.strip()]
    if lines:
        first_line = lines[0]
        start = content.find(first_line)
        if start >= 0:
            return start, start + len(first_line)

    return 0, len(content)


def _build_insert_after_patch(
    *,
    target_document_content: str,
    insertion_text: str,
) -> DraftedPatch:
    base_content = target_document_content.strip()
    if insertion_text.lower() in base_content.lower():
        return DraftedPatch(
            operation_type="replace_span",
            anchor={
                "exactText": base_content,
                "prefixText": "",
                "suffixText": "",
                "startOffset": 0,
                "endOffset": len(base_content),
            },
            expected_hash=_content_hash(base_content),
            before_preview=base_content,
            after_preview=base_content,
            document_preview_after=base_content,
            content_preview=base_content,
            rationale="El contenido solicitado ya existe en el documento objetivo.",
        )

    start, end = _choose_anchor_span(base_content)
    anchor_text = base_content[start:end]
    prefix = base_content[max(0, start - 48) : start]
    suffix = base_content[end : min(len(base_content), end + 48)]
    insertion_block = f"\n\n{insertion_text.strip()}"
    document_preview_after = f"{base_content[:end]}{insertion_block}{base_content[end:]}"
    return DraftedPatch(
        operation_type="insert_after_span",
        anchor={
            "exactText": anchor_text,
            "prefixText": prefix,
            "suffixText": suffix,
            "startOffset": start,
            "endOffset": end,
        },
        expected_hash=_content_hash(anchor_text),
        before_preview=anchor_text,
        after_preview=insertion_block,
        document_preview_after=document_preview_after,
        content_preview=document_preview_after,
        rationale="Insertar contenido nuevo despues del primer bloque relevante del documento.",
    )


class HeuristicFallbackPlanner:
    def plan_next_action(self, state: dict[str, Any]) -> PlannerDecision:
        user_message = state["user_message"].strip()
        available_documents = state.get("available_documents") or []
        context_view = state.get("context_view")
        search_matches = state.get("search_matches") or []
        iteration_count = int(state.get("iteration_count") or 0)
        is_edit = _message_mentions_edit(user_message)
        target_hint = _message_document_hint(user_message)
        max_iterations = int(state.get("max_iterations") or 6)
        max_patch_operations = int(state.get("max_patch_operations") or 1)

        if iteration_count >= max_iterations:
            return PlannerDecision(
                action_type="respond",
                intent="answer_question",
                response_content=(
                    "No pude seguir iterando con seguridad dentro del limite del runtime. "
                    "Intenta refinar la instruccion o revisar el documento objetivo."
                ),
                reasoning_summary="iteration_limit_reached",
            )

        if _is_simple_greeting(user_message):
            return PlannerDecision(
                action_type="respond",
                intent="answer_question",
                response_content=(
                    "Hola. Puedo responder preguntas del encounter o proponer patches "
                    "pequenos sobre una nota cuando me indiques el objetivo."
                ),
                reasoning_summary="simple_greeting_without_context",
            )

        if not available_documents:
            return PlannerDecision(
                action_type="call_tool",
                tool_name="list_open_documents",
                intent="edit_document" if is_edit else "answer_question",
                reasoning_summary="need_open_documents",
                target_document_hint=target_hint,
            )

        if not context_view:
            return PlannerDecision(
                action_type="call_tool",
                tool_name="build_context_view",
                tool_input={
                    "active_document_id": state.get("active_document_id"),
                    "include_document_ids": state.get("selected_document_ids", []),
                    "include_manual_context": True,
                },
                intent="edit_document" if is_edit else "answer_question",
                reasoning_summary="need_context_view_first",
                target_document_hint=target_hint,
            )

        if is_edit:
            if int(state.get("patch_operations_count") or 0) >= max_patch_operations:
                return PlannerDecision(
                    action_type="respond",
                    intent="edit_document",
                    response_content=(
                        "Ya consumi el presupuesto de propuestas de patch de este run. "
                        "Prueba una instruccion mas especifica."
                    ),
                    reasoning_summary="patch_budget_reached",
                    target_document_hint=target_hint,
                )

            target_document = _best_target_document(state, preferred_hint=target_hint)
            if not target_document:
                return PlannerDecision(
                    action_type="respond",
                    intent="edit_document",
                    response_content=(
                        "No encontre un documento editable adecuado dentro del workspace actual."
                    ),
                    reasoning_summary="no_editable_target_document",
                    target_document_hint=target_hint,
                )

            target_document_id = str(target_document["document_id"])
            document_summaries = state.get("document_summaries") or {}
            read_spans = state.get("read_spans") or []
            patch_history = state.get("patch_history") or {}

            if target_document_id not in document_summaries:
                return PlannerDecision(
                    action_type="call_tool",
                    tool_name="read_document_summary",
                    tool_input={"document_id": target_document_id},
                    intent="edit_document",
                    reasoning_summary="need_target_document_summary",
                    target_document_hint=target_hint,
                )

            if target_document_id not in patch_history:
                return PlannerDecision(
                    action_type="call_tool",
                    tool_name="read_patch_history",
                    tool_input={"document_id": target_document_id, "limit": 5},
                    intent="edit_document",
                    reasoning_summary="need_patch_history_context",
                    target_document_hint=target_hint,
                )

            has_target_span = any(
                str(read_span.get("document_id")) == target_document_id
                for read_span in read_spans
            )
            if not has_target_span:
                return PlannerDecision(
                    action_type="call_tool",
                    tool_name="read_document_span",
                    tool_input={
                        "document_id": target_document_id,
                        "max_chars": 1200,
                    },
                    intent="edit_document",
                    reasoning_summary="need_target_span_before_patch",
                    target_document_hint=target_hint,
                )

            proposal_tool = (
                "propose_insert_after_span"
                if _extract_requested_addition(user_message)
                else "propose_replace_span"
            )
            return PlannerDecision(
                action_type="call_tool",
                tool_name=proposal_tool,
                tool_input={"target_document_id": target_document_id},
                intent="edit_document",
                reasoning_summary="ready_to_propose_anchored_patch",
                target_document_hint=target_hint,
            )

        if search_matches:
            top_match = search_matches[0]
            return PlannerDecision(
                action_type="call_tool",
                tool_name="read_document_span",
                tool_input={
                    "document_id": str(top_match["document_id"]),
                    "exact_text": (top_match.get("anchor") or {}).get("exactText"),
                    "prefix_text": (top_match.get("anchor") or {}).get("prefixText"),
                    "suffix_text": (top_match.get("anchor") or {}).get("suffixText"),
                    "max_chars": 500,
                },
                intent="answer_question",
                reasoning_summary="need_focused_span_from_search_hit",
            )

        if not (state.get("read_spans") or state.get("read_documents")):
            return PlannerDecision(
                action_type="call_tool",
                tool_name="search_documents",
                tool_input={
                    "query": user_message,
                    "max_results": 3,
                    "allowed_document_types": ["note", "context", "transcription"],
                },
                intent="answer_question",
                reasoning_summary="need_search_after_context_view",
            )

        return PlannerDecision(
            action_type="respond",
            intent="answer_question",
            response_content=self._build_fallback_response(state),
            reasoning_summary="enough_context_to_respond",
        )

    def draft_patch_preview(
        self,
        *,
        state: dict[str, Any],
        target_document: dict[str, Any],
        target_document_content: str,
        supporting_context: list[dict[str, Any]],
        span_payload: dict[str, Any] | None = None,
    ) -> DraftedPatch:
        del target_document, supporting_context
        addition = _extract_requested_addition(state["user_message"])
        if addition:
            return _build_insert_after_patch(
                target_document_content=target_document_content,
                insertion_text=addition,
            )

        if span_payload and span_payload.get("content"):
            before_preview = str(span_payload["content"])
            anchor = span_payload.get("anchor") or {}
            rewritten_span = f"{before_preview}\n\n[Ajuste sugerido]: {state['user_message'].strip()}"
            document_preview_after = target_document_content.replace(before_preview, rewritten_span, 1)
            return DraftedPatch(
                operation_type="replace_span",
                anchor=anchor,
                expected_hash=_content_hash(before_preview),
                before_preview=before_preview,
                after_preview=rewritten_span,
                document_preview_after=document_preview_after,
                content_preview=document_preview_after,
                rationale="Reemplazar un span focalizado del documento con una version ajustada.",
            )

        base_content = target_document_content.strip()
        return DraftedPatch(
            operation_type="rewrite_document",
            anchor={
                "exactText": base_content,
                "prefixText": "",
                "suffixText": "",
                "startOffset": 0,
                "endOffset": len(base_content),
            },
            expected_hash=_content_hash(base_content),
            before_preview=base_content,
            after_preview=base_content,
            document_preview_after=base_content,
            content_preview=base_content,
            rationale="Fallback seguro sin cambios semanticos por falta de span focalizado.",
        )

    def _build_fallback_response(self, state: dict[str, Any]) -> str:
        context_view = state.get("context_view") or {}
        read_spans = state.get("read_spans") or []
        facts = context_view.get("facts") or []
        lines: list[str] = []
        if facts:
            rendered_facts = [
                f"{fact['value']}" for fact in facts[:2] if fact.get("value")
            ]
            if rendered_facts:
                lines.append("Contexto sintetizado: " + " | ".join(rendered_facts))
        if read_spans:
            rendered_spans = [
                f"{span.get('title')}: {_shorten_text(span.get('content'), 160)}"
                for span in read_spans[:2]
            ]
            lines.append("Lectura focalizada: " + " | ".join(rendered_spans))
        if not lines:
            lines.append("No encontre suficiente contexto relevante para responder con precision.")
        return " ".join(lines)


@dataclass
class VertexToolPlanner:
    settings: Settings
    fallback: HeuristicFallbackPlanner

    _initialized: bool = False
    _model: GenerativeModel | None = None

    def plan_next_action(self, state: dict[str, Any]) -> PlannerDecision:
        try:
            response_text = self._model_instance().generate_content(
                self._build_planner_prompt(state),
                generation_config=GenerationConfig(
                    temperature=0.1,
                    candidate_count=1,
                    response_mime_type="application/json",
                ),
            ).text
            return self._parse_decision(response_text, state)
        except Exception as error:
            logger.warning("Vertex planner failed, using fallback: %s", error)
            return self.fallback.plan_next_action(state)

    def draft_patch_preview(
        self,
        *,
        state: dict[str, Any],
        target_document: dict[str, Any],
        target_document_content: str,
        supporting_context: list[dict[str, Any]],
        span_payload: dict[str, Any] | None = None,
    ) -> DraftedPatch:
        try:
            response_text = self._model_instance().generate_content(
                self._build_patch_prompt(
                    state=state,
                    target_document=target_document,
                    target_document_content=target_document_content,
                    supporting_context=supporting_context,
                    span_payload=span_payload,
                ),
                generation_config=GenerationConfig(
                    temperature=0.2,
                    candidate_count=1,
                    response_mime_type="application/json",
                ),
            ).text
            return DraftedPatch.model_validate_json(_extract_json_object(response_text))
        except Exception as error:
            logger.warning("Vertex patch drafting failed, using fallback: %s", error)
            return self.fallback.draft_patch_preview(
                state=state,
                target_document=target_document,
                target_document_content=target_document_content,
                supporting_context=supporting_context,
                span_payload=span_payload,
            )

    def _model_instance(self) -> GenerativeModel:
        if self._model is not None:
            return self._model
        if not self._initialized:
            vertexai.init(
                project=self.settings.gcp_project_id,
                location=self.settings.gcp_region,
            )
            self._initialized = True
        self._model = GenerativeModel(self.settings.vertex_model)
        return self._model

    def _build_planner_prompt(self, state: dict[str, Any]) -> str:
        payload = {
            "user_message": state["user_message"],
            "active_document_id": state.get("active_document_id"),
            "available_documents": (state.get("available_documents") or [])[:8],
            "context_view": state.get("context_view"),
            "document_summaries": state.get("document_summaries"),
            "search_matches": (state.get("search_matches") or [])[:4],
            "read_spans": (state.get("read_spans") or [])[:4],
            "iteration_count": state.get("iteration_count"),
            "max_iterations": state.get("max_iterations"),
            "max_patch_operations": state.get("max_patch_operations"),
            "patch_operations_count": state.get("patch_operations_count"),
        }
        return (
            "Eres el planner del copiloto clinico. Debes decidir el siguiente paso "
            "dentro de un bounded tool loop por capas. Solo puedes devolver JSON valido "
            "con llaves: action_type, tool_name, tool_input, reasoning_summary, response_content, intent, target_document_hint. "
            "action_type solo puede ser call_tool o respond. "
            "tool_name solo puede ser: list_open_documents, list_encounter_documents, read_document_summary, "
            "read_document_span, search_documents, read_patch_history, build_context_view, "
            "propose_replace_span, propose_insert_after_span, propose_create_document. "
            "tool_input valido por tool: build_context_view solo admite active_document_id, include_document_ids, include_manual_context; "
            "read_document_summary y read_document_span usan document_id; propose_replace_span y propose_insert_after_span usan target_document_id. "
            "Reglas: saludos simples responden sin leer documentos; preguntas usan build_context_view antes de buscar spans; "
            "ediciones nunca terminan en respond y siempre deben pasar por read_document_summary/read_document_span antes de una tool propose_*; "
            "build_context_view no reemplaza la lectura del documento objetivo para editar. "
            "No uses markdown ni texto fuera del JSON.\n\n"
            f"STATE:\n{json.dumps(payload, ensure_ascii=False)}"
        )

    def _build_patch_prompt(
        self,
        *,
        state: dict[str, Any],
        target_document: dict[str, Any],
        target_document_content: str,
        supporting_context: list[dict[str, Any]],
        span_payload: dict[str, Any] | None = None,
    ) -> str:
        payload = {
            "user_message": state["user_message"],
            "target_document": {
                "document_id": str(target_document.get("document_id")),
                "title": target_document.get("title"),
                "type": target_document.get("type"),
            },
            "target_document_content": target_document_content,
            "span_payload": span_payload,
            "supporting_context": supporting_context[:4],
        }
        return (
            "Eres un redactor clinico que propone patches pequenos y anclados. "
            "Devuelve SOLO JSON valido con llaves: operation_type, anchor, expected_hash, before_preview, after_preview, "
            "document_preview_after, content_preview, rationale. "
            "operation_type debe ser replace_span, insert_after_span o rewrite_document. "
            "anchor debe usar exactText, prefixText, suffixText, startOffset y endOffset. "
            "content_preview puede repetir document_preview_after para compatibilidad. "
            "No agregues texto fuera del JSON.\n\n"
            f"PATCH_INPUT:\n{json.dumps(payload, ensure_ascii=False)}"
        )

    def _parse_decision(self, response_text: str, state: dict[str, Any]) -> PlannerDecision:
        try:
            raw_payload = json.loads(_extract_json_object(response_text))
            if raw_payload.get("tool_input") is None:
                raw_payload["tool_input"] = {}
            action_type = str(raw_payload.get("action_type") or "")
            tool_name = raw_payload.get("tool_name")
            if action_type == "call_tool":
                if tool_name not in ALLOWED_TOOL_NAMES:
                    raise ValueError("Planner returned unsupported tool_name")
                raw_payload["tool_input"] = _sanitize_tool_input(
                    tool_name,
                    raw_payload.get("tool_input"),
                )
            else:
                raw_payload["tool_input"] = {}
            raw_payload["intent"] = _canonical_intent(
                raw_intent=raw_payload.get("intent"),
                action_type=action_type,
                tool_name=tool_name,
                user_message=state["user_message"],
            )
            decision = PlannerDecision.model_validate(raw_payload)
        except (ValidationError, ValueError) as error:
            raise ValueError(f"Invalid planner response: {error}") from error

        if decision.action_type not in {"call_tool", "respond"}:
            raise ValueError("Planner returned unsupported action_type")
        if decision.action_type == "respond":
            if decision.intent == "edit_document":
                raise ValueError("Planner cannot finish an edit request with respond")
            if not decision.response_content:
                raise ValueError("Planner respond action requires response_content")
        return decision


def build_planner(settings: Settings) -> CopilotPlanner:
    fallback = HeuristicFallbackPlanner()
    return VertexToolPlanner(settings=settings, fallback=fallback)
