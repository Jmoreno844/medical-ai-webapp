from __future__ import annotations

from typing import Any, Mapping, Sequence
from xml.sax.saxutils import escape


def shorten_text(value: Any, *, max_length: int = 320) -> str:
    if value is None:
        return ""
    text = " ".join(str(value).split())
    return text[:max_length]


def xml_line(tag: str, value: Any, *, max_length: int = 320) -> str:
    return f"<{tag}>{escape(shorten_text(value, max_length=max_length))}</{tag}>"


def _has_value(value: Any) -> bool:
    return value not in (None, "", [], {}, False)


def _render_documents(
    documents: Sequence[Mapping[str, Any]],
    *,
    exclude_document_ids: set[str] | None = None,
) -> str:
    rendered_documents = [
        document
        for document in documents
        if str(document.get("document_id") or "") not in (exclude_document_ids or set())
    ]
    if not rendered_documents:
        return ""

    lines = ["<available_documents>"]
    for document in rendered_documents[:8]:
        lines.extend(
            [
                "  <document>",
                f"    {xml_line('document_id', document.get('document_id'))}",
                f"    {xml_line('title', document.get('title'))}",
                f"    {xml_line('doctype', document.get('type'))}",
                f"    {xml_line('status', document.get('status'))}",
                f"    {xml_line('is_active', document.get('is_active'))}",
                f"    {xml_line('is_open', document.get('is_open'))}",
                f"    {xml_line('ai_writable', document.get('ai_writable'))}",
                "  </document>",
            ]
        )
    lines.append("</available_documents>")
    return "\n".join(lines)


def _render_workspace_documents(
    workspace_index: Mapping[str, Any],
    *,
    active_document_id: str | None,
    selected_document_ids: Sequence[str],
) -> str:
    documents = list(workspace_index.get("documents") or [])
    if not documents:
        return ""

    relevant_ids: list[str] = []
    for candidate in [
        active_document_id,
        *(selected_document_ids or []),
        *(workspace_index.get("open_document_ids") or []),
    ]:
        candidate_id = str(candidate or "").strip()
        if candidate_id and candidate_id not in relevant_ids:
            relevant_ids.append(candidate_id)

    rendered_documents = [
        document
        for document in documents
        if not relevant_ids or str(document.get("document_id") or "") in relevant_ids
    ]
    if not rendered_documents:
        return ""

    lines = ["<workspace_documents>"]
    for document in rendered_documents[:8]:
        document_lines = [
            "  <workspace_document>",
            f"    {xml_line('document_id', document.get('document_id'))}",
            f"    {xml_line('title', document.get('title'))}",
            f"    {xml_line('doctype', document.get('type'))}",
            f"    {xml_line('status', document.get('status'))}",
            f"    {xml_line('is_active', document.get('is_active'))}",
            f"    {xml_line('is_open', document.get('is_open'))}",
            f"    {xml_line('ai_writable', document.get('ai_writable'))}",
        ]
        for field_name in ("has_user_edits", "has_streaming_state", "has_pending_patches"):
            if _has_value(document.get(field_name)):
                document_lines.append(f"    {xml_line(field_name, document.get(field_name))}")
        document_lines.append("  </workspace_document>")
        lines.extend(document_lines)
    lines.append("</workspace_documents>")
    return "\n".join(lines)


def _render_document_summaries(
    document_summaries: Mapping[str, Mapping[str, Any]],
    *,
    exclude_document_ids: set[str] | None = None,
) -> str:
    rendered_summaries = [
        (document_id, summary)
        for document_id, summary in document_summaries.items()
        if str(document_id) not in (exclude_document_ids or set())
    ]
    if not rendered_summaries:
        return ""

    lines = ["<document_summaries>"]
    for document_id, summary in rendered_summaries[:8]:
        lines.extend(
            [
                "  <document_summary>",
                f"    {xml_line('document_id', document_id)}",
                f"    {xml_line('title', summary.get('title'))}",
                f"    {xml_line('doctype', summary.get('type'))}",
                "  </document_summary>",
            ]
        )
    lines.append("</document_summaries>")
    return "\n".join(lines)


def _render_read_documents(read_documents: Sequence[Mapping[str, Any]]) -> str:
    # excerpt here is intentionally capped at 600 chars. This block appears in the
    # turn context header which is rebuilt and injected on EVERY planner iteration.
    # The full document content is already visible to the LLM via the ToolMessage
    # history (capped at 12000). Repeating the full text here would bloat the
    # context window across multi-turn runs with multiple document reads.
    if not read_documents:
        return ""

    lines = ["<read_documents>"]
    for document in read_documents[:6]:
        lines.extend(
            [
                "  <read_document>",
                f"    {xml_line('document_id', document.get('document_id'))}",
                f"    {xml_line('title', document.get('title'))}",
                f"    {xml_line('doctype', document.get('type'))}",
                f"    {xml_line('mode', document.get('mode'))}",
                "  </read_document>",
            ]
        )
    lines.append("</read_documents>")
    return "\n".join(lines)


def _render_read_spans(read_spans: Sequence[Mapping[str, Any]]) -> str:
    if not read_spans:
        return ""

    lines = ["<read_spans>"]
    for span in read_spans[:4]:
        lines.extend(
            [
                "  <read_span>",
                f"    {xml_line('document_id', span.get('document_id'))}",
                f"    {xml_line('title', span.get('title'))}",
                f"    {xml_line('start_offset', span.get('start_offset'))}",
                f"    {xml_line('end_offset', span.get('end_offset'))}",
                f"    {xml_line('content', span.get('content'), max_length=900)}",
                "  </read_span>",
            ]
        )
    lines.append("</read_spans>")
    return "\n".join(lines)


def _render_context_view(context_view: Mapping[str, Any] | None) -> str:
    if not context_view:
        return ""

    facts = list(context_view.get("facts") or [])[:6]
    if not facts:
        return ""

    lines = ["<context_view>"]
    for fact in facts:
        lines.extend(
            [
                "  <fact>",
                f"    {xml_line('category', fact.get('category'))}",
                f"    {xml_line('value', fact.get('value'))}",
                f"    {xml_line('source_document_id', fact.get('source_document_id'))}",
                "  </fact>",
            ]
        )
    lines.append("</context_view>")
    return "\n".join(lines)


def _render_patch_history(patch_history: Mapping[str, list[Mapping[str, Any]]]) -> str:
    if not patch_history:
        return ""

    lines = ["<patch_history>"]
    for document_id, patches in list(patch_history.items())[:4]:
        lines.append(f'  <document_patches document_id="{escape(str(document_id))}">')
        for patch in patches[:4]:
            lines.extend(
                [
                    "    <patch>",
                    f"      {xml_line('status', patch.get('status'))}",
                    f"      {xml_line('operation_type', patch.get('operation_type'))}",
                    f"      {xml_line('rationale', patch.get('rationale'))}",
                    "    </patch>",
                ]
            )
        lines.append("  </document_patches>")
    lines.append("</patch_history>")
    return "\n".join(lines)


def _render_search_results(
    search_results: Sequence[Mapping[str, Any]],
) -> str:
    if not search_results:
        return ""

    lines = ["<search_results>"]
    for result in search_results[:4]:
        lines.append(f'  <search_result query="{escape(str(result.get("query") or ""))}">')
        for match in (result.get("matches") or [])[:4]:
            lines.extend(
                [
                    "    <match>",
                    f"      {xml_line('document_id', match.get('document_id'))}",
                    f"      {xml_line('title', match.get('title'))}",
                    f"      {xml_line('snippet', match.get('snippet'))}",
                    "    </match>",
                ]
            )
        lines.append("  </search_result>")
    lines.append("</search_results>")
    return "\n".join(lines)


def _render_user_edit_notices(workspace_index: Mapping[str, Any]) -> str:
    # Emitted when the doctor typed in a document since the last copilot turn.
    # By the time the agent sees this, the chat submission path has already
    # force-saved the drafts, so the latest content is in the DB. The notice
    # is purely informational: if the user's instruction works on one of these
    # documents, the planner should call read_document to get the fresh text
    # rather than relying on any previous in-context snapshot.
    noticed_docs = [
        doc
        for doc in (workspace_index.get("documents") or [])
        if doc.get("ai_writable") and doc.get("has_user_edits")
    ]
    if not noticed_docs:
        return ""

    lines = ["<user_edit_notices>"]
    for doc in noticed_docs[:4]:
        lines.extend(
            [
                "  <notice>",
                f"    {xml_line('document_id', doc.get('document_id'))}",
                f"    {xml_line('title', doc.get('title'))}",
                "    <message>El medico edito este documento manualmente en este turno. "
                "La version mas reciente esta guardada. Si la instruccion del medico "
                "requiere trabajar sobre este documento (p. ej. 'traduce lo que escribi', "
                "'propaga este nuevo diagnostico'), debes leerlo primero con "
                "read_document para obtener el texto mas reciente.</message>",
                "  </notice>",
            ]
        )
    lines.append("</user_edit_notices>")
    return "\n".join(lines)


def _render_planning_state(state: Mapping[str, Any]) -> str:
    next_required_action = state.get("next_required_action")
    planned_target_document_id = state.get("planned_target_document_id")
    if not next_required_action and not planned_target_document_id:
        return ""

    lines = ["<planning_state>"]
    if next_required_action:
        lines.append(f"  {xml_line('next_required_action', next_required_action)}")
    if planned_target_document_id:
        lines.append(f"  {xml_line('planned_target_document_id', planned_target_document_id)}")
    lines.append("</planning_state>")
    return "\n".join(lines)



# Context is rendered as XML rather than JSON for two reasons:
# 1. Clinical text contains colons, braces, and quotes that require escaping in JSON,
#    which increases token count and parser ambiguity.
# 2. LLMs parse tagged XML structures with better fidelity when the content contains
#    medical abbreviations, nested lists, and multi-line prose.
def render_turn_context(state: Mapping[str, Any]) -> str:
    workspace_index = state.get("workspace_index") or {}
    selected_document_ids = list(state.get("selected_document_ids") or [])
    workspace_document_ids = {
        str(document.get("document_id") or "")
        for document in (workspace_index.get("documents") or [])
        if document.get("document_id") is not None
    }
    read_document_ids = {
        str(document.get("document_id") or "")
        for document in (state.get("read_documents") or [])
        if document.get("document_id") is not None
    }
    search_results = list(state.get("search_results") or [])
    if not search_results and state.get("search_matches"):
        search_results = [
            {
                "query": state.get("search_query"),
                "matches": state.get("search_matches") or [],
            }
        ]
    return "\n".join(
        filter(
            None,
            [
                "<copilot_turn_context>",
                f"  {xml_line('user_query', state.get('user_message'), max_length=1200)}",
                "  <workspace_index>",
                f"    {xml_line('active_document_id', state.get('active_document_id'))}",
                f"    {xml_line('selected_document_ids', ', '.join(selected_document_ids))}",
                "  </workspace_index>",
                _render_user_edit_notices(workspace_index) or None,
                _render_workspace_documents(
                    workspace_index,
                    active_document_id=state.get("active_document_id"),
                    selected_document_ids=selected_document_ids,
                ),
                _render_documents(
                    state.get("available_documents") or [],
                    exclude_document_ids=workspace_document_ids,
                ),
                _render_document_summaries(
                    state.get("document_summaries") or {},
                    exclude_document_ids=read_document_ids,
                ),
                _render_read_documents(state.get("read_documents") or []),
                _render_read_spans(state.get("read_spans") or []),
                _render_context_view(state.get("context_view")),
                _render_search_results(search_results),
                _render_patch_history(state.get("patch_history") or {}),
                _render_planning_state(state),
                (
                    f"  {xml_line('last_tool_error', state.get('last_tool_error'))}"
                    if state.get("last_tool_error")
                    else None
                ),
                (
                    f"  {xml_line('last_planner_error', state.get('last_planner_error'))}"
                    if state.get("last_planner_error")
                    else None
                ),
                "</copilot_turn_context>",
            ]
        )
    )


def render_patch_input(
    *,
    state: Mapping[str, Any],
    target_document: Mapping[str, Any],
    target_document_content: str,
    supporting_context: list[dict[str, Any]],
    span_payload: Mapping[str, Any] | None,
    requested_tool_name: str | None,
    requested_tool_instruction: str | None = None,
    requested_affected_sections: Sequence[str] | None = None,
) -> str:
    lines = [
        "<patch_drafting_input>",
        f"  {xml_line('user_query', state.get('user_message'), max_length=1400)}",
        f"  {xml_line('requested_tool_name', requested_tool_name)}",
        f"  {xml_line('requested_instruction', requested_tool_instruction)}",
        "  <target_document>",
        f"    {xml_line('document_id', target_document.get('document_id'))}",
        f"    {xml_line('title', target_document.get('title'))}",
        f"    {xml_line('type', target_document.get('type'))}",
        f"    {xml_line('version', target_document.get('version'))}",
        "  </target_document>",
        f"  {xml_line('target_document_content', target_document_content, max_length=12000)}",
    ]
    if span_payload:
        lines.extend(
            [
                "  <selected_span>",
                f"    {xml_line('start_offset', span_payload.get('start_offset'))}",
                f"    {xml_line('end_offset', span_payload.get('end_offset'))}",
                f"    {xml_line('content_hash', span_payload.get('content_hash'))}",
                "  </selected_span>",
            ]
        )
    lines.append("  <supporting_context>")
    for item in supporting_context[:8]:
        lines.extend(
            [
                "    <context_item>",
                f"      {xml_line('document_id', item.get('document_id'))}",
                f"      {xml_line('title', item.get('title'))}",
                f"      {xml_line('type', item.get('type'))}",
                f"      {xml_line('read_mode', item.get('read_mode'))}",
                f"      {xml_line('content', item.get('content'), max_length=12000)}",
                "    </context_item>",
            ]
        )
    lines.append("  </supporting_context>")
    # Inyectar el plan clínico del planner cuando está disponible.
    # El drafter usa <edit_plan> para saber exactamente qué secciones tocar y a qué nivel
    # de impacto clínico, sin necesidad de reinterpretar el historial de la conversación.
    clinical_plan = dict(state.get("clinical_plan") or {})
    if not clinical_plan and requested_affected_sections:
        clinical_plan = {
            "edit_scope": "local",
            "clinical_impact_level": "factual",
            "affected_sections": list(requested_affected_sections),
            "needs_full_note": False,
        }
    if clinical_plan:
        sections_str = ", ".join(clinical_plan.get("affected_sections") or [])
        lines.extend(
            [
                "  <edit_plan>",
                f"    {xml_line('edit_scope', clinical_plan.get('edit_scope'))}",
                f"    {xml_line('clinical_impact_level', clinical_plan.get('clinical_impact_level'))}",
                f"    {xml_line('affected_sections', sections_str)}",
                f"    {xml_line('needs_full_note', clinical_plan.get('needs_full_note'))}",
            ]
        )
        if requested_affected_sections:
            lines.append(
                f"    {xml_line('requested_affected_sections', ', '.join(requested_affected_sections))}"
            )
        if clinical_plan.get("reasoning"):
            # Razonamiento clínico interno del planner: explica el hilo causal del cambio.
            lines.append(f"    {xml_line('reasoning', clinical_plan.get('reasoning'), max_length=800)}")
        section_instructions = clinical_plan.get("section_instructions") or {}
        if section_instructions:
            # Instrucciones quirúrgicas por sección: el drafter las prioriza sobre
            # inferir el cambio desde reasoning o user_query.
            lines.append("    <section_instructions>")
            for section_name, instruction in section_instructions.items():
                lines.append(f"      <instruction section=\"{section_name}\">{instruction}</instruction>")
            lines.append("    </section_instructions>")
        lines.append("  </edit_plan>")
    lines.append("</patch_drafting_input>")
    return "\n".join(lines)
