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


def _render_documents(documents: Sequence[Mapping[str, Any]]) -> str:
    if not documents:
        return "<available_documents />"

    lines = ["<available_documents>"]
    for document in documents[:8]:
        lines.extend(
            [
                "  <document>",
                f"    {xml_line('document_id', document.get('document_id'))}",
                f"    {xml_line('title', document.get('title'))}",
                f"    {xml_line('type', document.get('type'))}",
                f"    {xml_line('status', document.get('status'))}",
                f"    {xml_line('version', document.get('version'))}",
                f"    {xml_line('is_active', document.get('is_active'))}",
                f"    {xml_line('is_open', document.get('is_open'))}",
                f"    {xml_line('ai_writable', document.get('ai_writable'))}",
                f"    {xml_line('excerpt', document.get('excerpt'))}",
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
        return "<workspace_documents />"

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
        return "<workspace_documents />"

    lines = ["<workspace_documents>"]
    for document in rendered_documents[:8]:
        lines.extend(
            [
                "  <workspace_document>",
                f"    {xml_line('document_id', document.get('document_id'))}",
                f"    {xml_line('title', document.get('title'))}",
                f"    {xml_line('type', document.get('type'))}",
                f"    {xml_line('status', document.get('status'))}",
                f"    {xml_line('is_active', document.get('is_active'))}",
                f"    {xml_line('is_open', document.get('is_open'))}",
                f"    {xml_line('ai_writable', document.get('ai_writable'))}",
                f"    {xml_line('excerpt', document.get('excerpt'))}",
                f"    {xml_line('short_summary', document.get('short_summary'))}",
                "  </workspace_document>",
            ]
        )
    lines.append("</workspace_documents>")
    return "\n".join(lines)


def _render_document_summaries(document_summaries: Mapping[str, Mapping[str, Any]]) -> str:
    if not document_summaries:
        return "<document_summaries />"

    lines = ["<document_summaries>"]
    for document_id, summary in list(document_summaries.items())[:8]:
        lines.extend(
            [
                "  <document_summary>",
                f"    {xml_line('document_id', document_id)}",
                f"    {xml_line('title', summary.get('title'))}",
                f"    {xml_line('type', summary.get('type'))}",
                f"    {xml_line('version', summary.get('version'))}",
                f"    {xml_line('short_summary', summary.get('short_summary'))}",
                f"    {xml_line('excerpt', summary.get('excerpt'))}",
                "  </document_summary>",
            ]
        )
    lines.append("</document_summaries>")
    return "\n".join(lines)


def _render_read_documents(read_documents: Sequence[Mapping[str, Any]]) -> str:
    if not read_documents:
        return "<read_documents />"

    lines = ["<read_documents>"]
    for document in read_documents[:6]:
        lines.extend(
            [
                "  <read_document>",
                f"    {xml_line('document_id', document.get('document_id'))}",
                f"    {xml_line('title', document.get('title'))}",
                f"    {xml_line('type', document.get('type'))}",
                f"    {xml_line('mode', document.get('mode'))}",
                f"    {xml_line('short_summary', document.get('short_summary'))}",
                f"    {xml_line('excerpt', document.get('excerpt'), max_length=900)}",
                "  </read_document>",
            ]
        )
    lines.append("</read_documents>")
    return "\n".join(lines)


def _render_read_spans(read_spans: Sequence[Mapping[str, Any]]) -> str:
    if not read_spans:
        return "<read_spans />"

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
        return "<context_view />"

    lines = ["<context_view>"]
    for fact in (context_view.get("facts") or [])[:6]:
        lines.extend(
            [
                "  <fact>",
                f"    {xml_line('category', fact.get('category'))}",
                f"    {xml_line('value', fact.get('value'))}",
                f"    {xml_line('source_document_id', fact.get('source_document_id'))}",
                f"    {xml_line('confidence', fact.get('confidence'))}",
                "  </fact>",
            ]
        )
    lines.append("</context_view>")
    return "\n".join(lines)


def _render_patch_history(patch_history: Mapping[str, list[Mapping[str, Any]]]) -> str:
    if not patch_history:
        return "<patch_history />"

    lines = ["<patch_history>"]
    for document_id, patches in list(patch_history.items())[:4]:
        lines.append(f'  <document_patches document_id="{escape(str(document_id))}">')
        for patch in patches[:4]:
            lines.extend(
                [
                    "    <patch>",
                    f"      {xml_line('patch_id', patch.get('patch_id'))}",
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
        return "<search_results />"

    lines = ["<search_results>"]
    for result in search_results[:4]:
        lines.append(f'  <search_result query="{escape(str(result.get("query") or ""))}">')
        for match in (result.get("matches") or [])[:4]:
            lines.extend(
                [
                    "    <match>",
                    f"      {xml_line('document_id', match.get('document_id'))}",
                    f"      {xml_line('title', match.get('title'))}",
                    f"      {xml_line('score', match.get('score'))}",
                    f"      {xml_line('snippet', match.get('snippet'))}",
                    "    </match>",
                ]
            )
        lines.append("  </search_result>")
    lines.append("</search_results>")
    return "\n".join(lines)


def render_turn_context(state: Mapping[str, Any]) -> str:
    workspace_index = state.get("workspace_index") or {}
    selected_document_ids = list(state.get("selected_document_ids") or [])
    search_results = list(state.get("search_results") or [])
    if not search_results and state.get("search_matches"):
        search_results = [
            {
                "query": state.get("search_query"),
                "matches": state.get("search_matches") or [],
            }
        ]
    return "\n".join(
        [
            "<copilot_turn_context>",
            f"  {xml_line('user_query', state.get('user_message'), max_length=1200)}",
            "  <workspace_index>",
            f"    {xml_line('encounter_id', workspace_index.get('encounter_id'))}",
            f"    {xml_line('workspace_version', workspace_index.get('workspace_version'))}",
            f"    {xml_line('active_document_id', state.get('active_document_id'))}",
            f"    {xml_line('selected_document_ids', ', '.join(selected_document_ids))}",
            "  </workspace_index>",
            _render_workspace_documents(
                workspace_index,
                active_document_id=state.get("active_document_id"),
                selected_document_ids=selected_document_ids,
            ),
            _render_documents(state.get("available_documents") or []),
            _render_document_summaries(state.get("document_summaries") or {}),
            _render_read_documents(state.get("read_documents") or []),
            _render_read_spans(state.get("read_spans") or []),
            _render_context_view(state.get("context_view")),
            _render_search_results(search_results),
            _render_patch_history(state.get("patch_history") or {}),
            "  <budgets>",
            f"    {xml_line('iteration_count', state.get('iteration_count'))}",
            f"    {xml_line('max_iterations', state.get('max_iterations'))}",
            f"    {xml_line('patch_operations_count', state.get('patch_operations_count'))}",
            f"    {xml_line('max_patch_operations', state.get('max_patch_operations'))}",
            "  </budgets>",
            f"  {xml_line('last_tool_error', state.get('last_tool_error'))}",
            f"  {xml_line('last_planner_error', state.get('last_planner_error'))}",
            "</copilot_turn_context>",
        ]
    )


def render_patch_input(
    *,
    state: Mapping[str, Any],
    target_document: Mapping[str, Any],
    target_document_content: str,
    supporting_context: list[dict[str, Any]],
    span_payload: Mapping[str, Any] | None,
    requested_tool_name: str | None,
) -> str:
    lines = [
        "<patch_drafting_input>",
        f"  {xml_line('user_query', state.get('user_message'), max_length=1400)}",
        f"  {xml_line('requested_tool_name', requested_tool_name)}",
        "  <target_document>",
        f"    {xml_line('document_id', target_document.get('document_id'))}",
        f"    {xml_line('title', target_document.get('title'))}",
        f"    {xml_line('type', target_document.get('type'))}",
        f"    {xml_line('version', target_document.get('version'))}",
        "  </target_document>",
        f"  {xml_line('target_document_content', target_document_content, max_length=4000)}",
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
                f"      {xml_line('excerpt', item.get('excerpt'), max_length=800)}",
                "    </context_item>",
            ]
        )
    lines.extend(["  </supporting_context>", "</patch_drafting_input>"])
    return "\n".join(lines)
