from __future__ import annotations

import uuid
import unicodedata
from typing import Any, Protocol, cast

from app.graph.state import CopilotState
from app.planner import CopilotPlanner


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

    def read_encounter_context(self) -> dict[str, Any]: ...

    def build_context_view(
        self,
        *,
        active_document_id: str | None = None,
        include_document_ids: list[str] | None = None,
        include_manual_context: bool = True,
    ) -> dict[str, Any]: ...


DOCUMENT_TITLE_FAMILIES = {
    "clinical_note": {
        "nota",
        "nota clinica",
        "historia clinica",
        "soap",
        "evolucion",
        "evolucion clinica",
    },
    "discharge_note": {
        "egreso",
        "epicrisis",
        "discharge",
    },
    "context": {
        "contexto",
        "contexto del encuentro",
    },
    "transcription": {
        "transcripcion",
        "transcript",
    },
}


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _shorten_text(content: str | None, *, max_length: int = 220) -> str:
    if not content:
        return ""
    return " ".join(content.split())[:max_length].strip()


def _default_selected_document_ids(state: CopilotState) -> list[str]:
    available_documents = state.get("available_documents") or []
    available_document_ids = {
        str(document["document_id"]) for document in available_documents
    }

    selected_document_ids = [
        document_id
        for document_id in state.get("selected_document_ids", [])
        if document_id in available_document_ids
    ]
    if selected_document_ids:
        return selected_document_ids

    selected_document_ids = [
        str(document["document_id"])
        for document in available_documents
        if document.get("is_active") or document.get("pinned_for_agent")
    ]
    if selected_document_ids:
        return selected_document_ids

    return [str(document["document_id"]) for document in available_documents[:2]]


def _document_family(document: dict[str, Any]) -> str | None:
    document_type = _normalize_text(str(document.get("type") or "").lower())
    if document_type == "note":
        title = _normalize_text(str(document.get("title") or "").lower())
        if any(alias in title for alias in DOCUMENT_TITLE_FAMILIES["discharge_note"]):
            return "discharge_note"
        return "clinical_note"
    if document_type in {"context", "transcription"}:
        return document_type

    title = _normalize_text(str(document.get("title") or "").lower())
    for family, aliases in DOCUMENT_TITLE_FAMILIES.items():
        if any(alias in title for alias in aliases):
            return family
    return None


def _prompt_document_families(user_message: str) -> set[str]:
    normalized_message = _normalize_text(user_message.lower())
    families: set[str] = set()
    for family, aliases in DOCUMENT_TITLE_FAMILIES.items():
        if any(alias in normalized_message for alias in aliases):
            families.add(family)
    return families


def _score_target_document(
    state: CopilotState,
    document: dict[str, Any],
    *,
    preferred_hint: str | None = None,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    document_id = str(document["document_id"])
    prompt = _normalize_text(state["user_message"].lower())
    prompt_families = _prompt_document_families(state["user_message"])
    title = _normalize_text(str(document.get("title") or "").lower())
    family = _document_family(document)
    selected_document_ids = {
        str(selected_document_id)
        for selected_document_id in state.get("selected_document_ids", [])
    }

    if preferred_hint:
        normalized_hint = _normalize_text(preferred_hint.lower())
        if normalized_hint in title:
            score += 40
            reasons.append(f"target_hint_match:{normalized_hint}")

    if document_id == str(state.get("active_document_id") or ""):
        score += 20
        reasons.append("active_document")
    if document_id in selected_document_ids:
        score += 14
        reasons.append("selected_document")
    if document.get("pinned_for_agent"):
        score += 4
        reasons.append("pinned_for_agent")

    if family == "clinical_note":
        score += 12
        reasons.append("writable_clinical_note")
    elif family == "discharge_note":
        score += 10
        reasons.append("writable_discharge_document")
    elif family == "context":
        score -= 24
        reasons.append("context_penalty")
    elif family == "transcription":
        score -= 32
        reasons.append("transcription_penalty")

    if prompt_families and family in prompt_families:
        score += 50
        reasons.append(f"title_family_match:{family}")

    if title and any(token in title for token in prompt.split()):
        score += 8
        reasons.append("title_token_overlap")

    if family in {"context", "transcription"} and prompt_families:
        score -= 20
        reasons.append("prompt_prefers_named_editable_document")

    return score, reasons


def _target_document_candidates(state: CopilotState) -> list[dict[str, Any]]:
    available_documents = state.get("available_documents") or state.get("workspace_index", {}).get(
        "documents",
        []
    )
    return [
        document
        for document in available_documents
        if document.get("ai_writable", True)
    ]


def _resolve_target_document(
    state: CopilotState,
    *,
    preferred_hint: str | None = None,
    explicit_document_id: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    candidates = _target_document_candidates(state)
    if explicit_document_id:
        for document in candidates:
            if str(document["document_id"]) == str(explicit_document_id):
                return document, "explicit_document_id"
    if not candidates:
        return None, None

    scored_candidates = [
        (*_score_target_document(state, document, preferred_hint=preferred_hint), document)
        for document in candidates
    ]
    best_score, best_reasons, best_document = max(
        ((score, reasons, document) for score, reasons, document in scored_candidates),
        key=lambda item: item[0],
    )
    reason = ", ".join(best_reasons) if best_reasons else "fallback_first_writable"
    return best_document, f"{reason}; score={best_score}"


def _upsert_read_document(
    read_documents: list[dict[str, Any]], document: dict[str, Any]
) -> list[dict[str, Any]]:
    document_id = str(document["document_id"])
    remaining_documents = [
        existing_document
        for existing_document in read_documents
        if str(existing_document["document_id"]) != document_id
    ]
    return [*remaining_documents, document]


def _upsert_read_span(
    read_spans: list[dict[str, Any]], span: dict[str, Any]
) -> list[dict[str, Any]]:
    document_id = str(span["document_id"])
    remaining_spans = [
        existing_span
        for existing_span in read_spans
        if not (
            str(existing_span["document_id"]) == document_id
            and existing_span.get("start_offset") == span.get("start_offset")
            and existing_span.get("end_offset") == span.get("end_offset")
        )
    ]
    return [*remaining_spans, span]


def _build_retrieved_context(state: CopilotState) -> list[dict[str, Any]]:
    context_view = state.get("context_view") or {}
    read_spans = state.get("read_spans") or []
    context_items = [
        {
            "type": "context_fact",
            "document_id": fact["source_document_id"],
            "title": f"Fact {index + 1}",
            "excerpt": fact["value"],
            "read_mode": "context_view",
        }
        for index, fact in enumerate(context_view.get("facts") or [])
    ]
    span_items = [
        {
            "type": span.get("type", "document_span"),
            "document_id": span["document_id"],
            "title": span.get("title"),
            "excerpt": _shorten_text(span.get("content"), max_length=320),
            "read_mode": "span",
        }
        for span in read_spans
    ]
    return [*context_items, *span_items]


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
        return f"{len(payload.get('matches', []))} coincidencia(s) para '{payload.get('query')}'"
    if tool_name == "read_patch_history":
        return f"Historial de {len(payload.get('patches', []))} patch(es)"
    if tool_name == "build_context_view":
        return f"Vista de contexto con {len(payload.get('facts', []))} fact(s)"
    if tool_name in {"propose_replace_span", "propose_insert_after_span", "propose_create_document"}:
        return f"Patch listo para {payload.get('target_document_id')}"
    return "resultado de tool procesado"


def make_plan_or_next_action_node(planner: CopilotPlanner):
    def plan_or_next_action(state: CopilotState) -> CopilotState:
        next_state = cast(CopilotState, dict(state))
        decision = planner.plan_next_action(next_state)
        next_state["intent"] = decision.intent or next_state.get("intent")
        next_state["pending_action"] = decision.model_dump(mode="python")
        next_state["current_plan_step"] = decision.action_type
        next_state["planner_decisions"] = [
            *(next_state.get("planner_decisions") or []),
            decision.model_dump(mode="python"),
        ]
        next_state["proposed_action"] = decision.action_type

        if decision.action_type == "respond":
            next_state["final_response"] = decision.response_content
            next_state["requires_human_review"] = False
        return next_state

    return plan_or_next_action


def make_call_tool_node(
    tools_client: LayeredToolsClient,
    planner: CopilotPlanner,
):
    def call_tool(state: CopilotState) -> CopilotState:
        next_state = cast(CopilotState, dict(state))
        pending_action = next_state.get("pending_action") or {}
        tool_name = pending_action.get("tool_name")
        tool_input = pending_action.get("tool_input") or {}

        if tool_name == "list_open_documents":
            payload = tools_client.list_open_documents(next_state["workspace_index"])
        elif tool_name == "list_encounter_documents":
            payload = tools_client.list_encounter_documents()
        elif tool_name == "read_document_summary":
            document_id = str(
                tool_input.get("document_id") or next_state.get("active_document_id") or ""
            )
            payload = tools_client.read_document_summary(document_id)
        elif tool_name == "read_document_span":
            document_id = str(
                tool_input.get("document_id") or next_state.get("active_document_id") or ""
            )
            payload = tools_client.read_document_span(
                document_id,
                exact_text=tool_input.get("exact_text"),
                prefix_text=tool_input.get("prefix_text"),
                suffix_text=tool_input.get("suffix_text"),
                start_offset=tool_input.get("start_offset"),
                end_offset=tool_input.get("end_offset"),
                max_chars=int(tool_input.get("max_chars") or 600),
            )
        elif tool_name == "search_documents":
            payload = tools_client.search_documents(
                query=str(tool_input.get("query") or next_state["user_message"]),
                max_results=int(tool_input.get("max_results") or 3),
                allowed_document_types=tool_input.get("allowed_document_types") or None,
            )
        elif tool_name == "read_patch_history":
            document_id = str(
                tool_input.get("document_id") or next_state.get("active_document_id") or ""
            )
            payload = tools_client.read_patch_history(
                document_id,
                limit=int(tool_input.get("limit") or 5),
            )
        elif tool_name == "read_encounter_context":
            payload = tools_client.read_encounter_context()
        elif tool_name == "build_context_view":
            payload = tools_client.build_context_view(
                active_document_id=tool_input.get("active_document_id")
                or next_state.get("active_document_id"),
                include_document_ids=tool_input.get("include_document_ids")
                or next_state.get("selected_document_ids", []),
                include_manual_context=bool(tool_input.get("include_manual_context", True)),
            )
        elif tool_name in {"propose_replace_span", "propose_insert_after_span", "propose_create_document"}:
            target_document, selection_reason = _resolve_target_document(
                next_state,
                preferred_hint=pending_action.get("target_document_hint"),
                explicit_document_id=tool_input.get("target_document_id"),
            )
            if not target_document:
                payload = {"error": "No editable target document found"}
            else:
                target_document_id = str(target_document["document_id"])
                summary_map = next_state.get("document_summaries") or {}
                span_payload = next(
                    (
                        span
                        for span in (next_state.get("read_spans") or [])
                        if str(span["document_id"]) == target_document_id
                    ),
                    None,
                )
                if not span_payload:
                    span_payload = tools_client.read_document_span(
                        target_document_id,
                        max_chars=1200,
                    )
                summary_payload = summary_map.get(target_document_id) or tools_client.read_document_summary(
                    target_document_id
                )
                drafted_patch = planner.draft_patch_preview(
                    state=next_state,
                    target_document=target_document,
                    target_document_content=str(span_payload.get("content") or ""),
                    supporting_context=next_state.get("retrieved_context") or [],
                    span_payload=span_payload,
                )
                payload = {
                    "patch_id": str(uuid.uuid4()),
                    "target_document_id": target_document_id,
                    "target_document_title": str(
                        target_document.get("title") or target_document_id
                    ),
                    "target_selection_reason": selection_reason,
                    "base_version": int(summary_payload.get("version") or target_document.get("version") or 1),
                    "operation_type": drafted_patch.operation_type,
                    "anchor": drafted_patch.anchor,
                    "expected_hash": drafted_patch.expected_hash,
                    "before_preview": drafted_patch.before_preview,
                    "after_preview": drafted_patch.after_preview,
                    "document_preview_after": drafted_patch.document_preview_after,
                    "content_preview": drafted_patch.content_preview,
                    "rationale": drafted_patch.rationale,
                    "source_context_document_ids": [
                        str(document["document_id"])
                        for document in next_state.get("read_documents", [])
                    ],
                    "read_document": {
                        "document_id": target_document_id,
                        "title": summary_payload.get("title") or target_document.get("title"),
                        "type": summary_payload.get("type") or target_document.get("type"),
                        "mode": "span",
                        "content": span_payload.get("content"),
                        "excerpt": _shorten_text(span_payload.get("content"), max_length=320),
                    },
                }
        else:
            payload = {"error": f"Unsupported tool: {tool_name}"}

        next_state["tool_calls"] = [
            *(next_state.get("tool_calls") or []),
            {
                "tool_name": tool_name,
                "tool_input": tool_input,
                "reasoning_summary": pending_action.get("reasoning_summary"),
            },
        ]
        next_state["pending_tool_result"] = {
            "tool_name": tool_name,
            "payload": payload,
            "summary": _summarize_tool_result(tool_name or "unknown", payload),
        }
        next_state["iteration_count"] = int(next_state.get("iteration_count") or 0) + 1
        return next_state

    return call_tool


def accumulate_observation(state: CopilotState) -> CopilotState:
    next_state = cast(CopilotState, dict(state))
    pending_tool_result = next_state.get("pending_tool_result")
    if not pending_tool_result:
        return next_state

    tool_name = pending_tool_result["tool_name"]
    payload = pending_tool_result["payload"]

    if payload.get("error"):
        next_state["final_response"] = (
            "No pude completar una accion del copiloto con seguridad. "
            f"Detalle: {payload['error']}"
        )
        next_state["requires_human_review"] = False
    elif tool_name in {"list_open_documents", "list_encounter_documents"}:
        next_state["available_documents"] = payload.get("documents", [])
        next_state["selected_document_ids"] = _default_selected_document_ids(next_state)
    elif tool_name == "read_document_summary":
        summary_map = dict(next_state.get("document_summaries") or {})
        summary_map[str(payload["document_id"])] = payload
        next_state["document_summaries"] = summary_map
        next_state["read_documents"] = _upsert_read_document(
            next_state.get("read_documents") or [],
            {
                "document_id": payload["document_id"],
                "title": payload["title"],
                "type": payload["type"],
                "mode": "summary",
                "excerpt": payload.get("excerpt"),
                "content": None,
            },
        )
        next_state["retrieved_context"] = _build_retrieved_context(next_state)
    elif tool_name == "read_document_span":
        summary_map = next_state.get("document_summaries") or {}
        title = (summary_map.get(str(payload["document_id"])) or {}).get("title")
        document_type = (summary_map.get(str(payload["document_id"])) or {}).get("type")
        span = {
            **payload,
            "title": title,
            "type": document_type,
        }
        next_state["read_spans"] = _upsert_read_span(next_state.get("read_spans") or [], span)
        next_state["read_documents"] = _upsert_read_document(
            next_state.get("read_documents") or [],
            {
                "document_id": payload["document_id"],
                "title": title,
                "type": document_type,
                "mode": "span",
                "content": payload.get("content"),
                "excerpt": _shorten_text(payload.get("content"), max_length=320),
            },
        )
        next_state["retrieved_context"] = _build_retrieved_context(next_state)
    elif tool_name == "search_documents":
        next_state["search_query"] = payload.get("query")
        next_state["search_matches"] = payload.get("matches", [])
    elif tool_name == "read_patch_history":
        patch_history = dict(next_state.get("patch_history") or {})
        patch_history[str(payload["document_id"])] = payload.get("patches", [])
        next_state["patch_history"] = patch_history
    elif tool_name == "read_encounter_context":
        next_state["encounter_context"] = payload
    elif tool_name == "build_context_view":
        next_state["context_view"] = payload
        next_state["retrieved_context"] = _build_retrieved_context(next_state)
    elif tool_name in {"propose_replace_span", "propose_insert_after_span", "propose_create_document"}:
        read_document = payload.get("read_document")
        if read_document:
            next_state["read_documents"] = _upsert_read_document(
                next_state.get("read_documents") or [],
                read_document,
            )
            next_state["retrieved_context"] = _build_retrieved_context(next_state)
        next_state["patch_id"] = payload["patch_id"]
        next_state["target_document_id"] = payload["target_document_id"]
        next_state["target_document_title"] = payload["target_document_title"]
        next_state["target_selection_reason"] = payload["target_selection_reason"]
        next_state["base_version"] = payload["base_version"]
        next_state["patch_preview"] = {
            "patch_id": payload["patch_id"],
            "target_document_id": payload["target_document_id"],
            "base_version": payload["base_version"],
            "operation_type": payload["operation_type"],
            "anchor": payload["anchor"],
            "expected_hash": payload.get("expected_hash"),
            "before_preview": payload.get("before_preview"),
            "after_preview": payload.get("after_preview"),
            "document_preview_after": payload.get("document_preview_after"),
            "rationale": payload["rationale"],
            "content_preview": payload["content_preview"],
            "source_context_document_ids": payload["source_context_document_ids"],
            "target_document_title": payload["target_document_title"],
            "target_selection_reason": payload["target_selection_reason"],
        }
        next_state["requires_human_review"] = True
        next_state["final_response"] = None
        next_state["patch_operations_count"] = int(next_state.get("patch_operations_count") or 0) + 1

    next_state["tool_results"] = [
        *(next_state.get("tool_results") or []),
        {
            "tool_name": tool_name,
            "summary": pending_tool_result["summary"],
            "payload": payload,
        },
    ]
    next_state["pending_tool_result"] = None
    next_state["pending_action"] = None
    return next_state


def interrupt_for_review(state: CopilotState) -> CopilotState:
    return cast(CopilotState, dict(state))


def apply_patch(state: CopilotState) -> CopilotState:
    return cast(CopilotState, dict(state))


def finalize_response(state: CopilotState) -> CopilotState:
    next_state = cast(CopilotState, dict(state))
    if next_state.get("patch_preview"):
        return next_state

    if next_state.get("final_response"):
        return next_state

    next_state["final_response"] = (
        "No pude completar la solicitud del copiloto dentro de los limites de este run."
    )
    next_state["requires_human_review"] = False
    return next_state
