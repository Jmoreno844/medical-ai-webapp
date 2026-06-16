from __future__ import annotations

import json

import streamlit as st

from common.llm_response import (
    output_token_breakdown_from_usage,
    reasoning_tokens_from_usage,
)
from common.usage_cost import parse_token_usage
from ui.cluster_lookup import ClusterTurnsView, cluster_turns_from_generation_payload
from ui.linked_evidence_audit import (
    CONTENT_VIEW_APPLIED,
    CONTENT_VIEW_SOURCE,
    RENDERER_STEP,
    display_generation_content,
    format_cited_evidence_ids_caption,
    is_legacy_two_step_section,
    is_two_step_section_output,
    planner_raw_output,
    resolve_llm_response_by_step,
)
from ui.triage_audit import (
    DISPOSITION_CONTENT,
    DISPOSITION_DROPPED,
    DISPOSITION_DROPPED_AND_CONTENT,
    DISPOSITION_UNCLASSIFIED,
    triage_item_disposition_rows,
)
from ui.latency import (
    clustering_has_split_latency,
    clustering_latency_ms,
    e2e_latency_rows,
    format_latency_ms,
    latency_breakdown_rows,
    primary_latency_ms,
    secondary_latency_ms,
)

_CLUSTER_COLORS = [
    "#2196F3",  # blue
    "#FF9800",  # orange
    "#9C27B0",  # purple
    "#4CAF50",  # green
    "#F44336",  # red
    "#00BCD4",  # cyan
    "#FF5722",  # deep-orange
    "#607D8B",  # blue-grey
]

_SECTION_COLORS = [
    "#4CAF50",
    "#2196F3",
    "#9C27B0",
    "#FF9800",
    "#F44336",
    "#00BCD4",
]


def _cluster_color(index: int) -> str:
    return _CLUSTER_COLORS[index % len(_CLUSTER_COLORS)]


def _section_color(index: int) -> str:
    return _SECTION_COLORS[index % len(_SECTION_COLORS)]


def render_json_expander(
    payload: dict[str, object],
    *,
    title: str = "JSON completo",
) -> None:
    with st.expander(title):
        st.code(json.dumps(payload, indent=2, ensure_ascii=False), language="json")


def render_step_latency(step: str, payload: dict[str, object]) -> None:
    if step == "clustering" and clustering_has_split_latency(payload):
        initial_ms, repair_ms = clustering_latency_ms(payload)
        if initial_ms is None:
            return

        if repair_ms is not None and repair_ms > 0:
            col_initial, col_repair, col_total = st.columns(3)
            col_initial.metric(
                "Clustering inicial",
                format_latency_ms(initial_ms),
            )
            col_repair.metric(
                "Repair missing turns",
                format_latency_ms(repair_ms),
            )
            col_total.metric(
                "Total LLM",
                format_latency_ms(initial_ms + repair_ms),
            )
        else:
            st.metric(
                "Clustering inicial",
                format_latency_ms(initial_ms),
            )

        breakdown = latency_breakdown_rows(step, payload)
        if breakdown:
            with st.expander("Detalle de latencia por repair pass"):
                st.dataframe(breakdown, use_container_width=True, hide_index=True)
        return

    primary_ms = primary_latency_ms(step, payload)
    if primary_ms is None:
        return

    secondary_ms = secondary_latency_ms(step, payload)
    breakdown = latency_breakdown_rows(step, payload)

    if secondary_ms is not None and secondary_ms != primary_ms:
        col_primary, col_secondary = st.columns(2)
        col_primary.metric(
            "Latencia paso",
            format_latency_ms(primary_ms),
            help="Tiempo de reloj del paso completo.",
        )
        col_secondary.metric(
            "LLM acumulado",
            format_latency_ms(secondary_ms),
            help="Suma de latencias por batch/sección (puede ser mayor si hay paralelismo).",
        )
    else:
        st.metric(
            "Latencia",
            format_latency_ms(primary_ms),
            help="Tiempo de reloj del paso completo.",
        )

    if breakdown:
        with st.expander("Detalle de latencia por llamada"):
            st.dataframe(breakdown, use_container_width=True, hide_index=True)


def render_e2e_latency_summary(outputs: list[dict[str, object]]) -> None:
    rows = e2e_latency_rows(outputs)
    if not rows:
        return
    st.markdown("**Latencia por paso**")
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.divider()


def _render_section_source_turns_content(
    *,
    heading: str,
    section_id: str,
    clusters: list[ClusterTurnsView],
) -> None:
    st.markdown(f"**{heading}** · `{section_id}`")
    if not clusters:
        st.warning(
            "No se pudieron cargar los clusters. "
            "Verifica que `cases_file` del resultado apunte al índice de clusters."
        )
        return

    total_turns = sum(len(cluster.turns) for cluster in clusters)
    col_a, col_b = st.columns(2)
    col_a.metric("Clusters", len(clusters))
    col_b.metric("Turnos", total_turns)

    for index, cluster in enumerate(clusters):
        color = _cluster_color(index)
        st.markdown(
            f'<div style="border-left:3px solid {color};'
            f'padding:2px 10px;margin-top:12px">'
            f"<strong>{cluster.topic_label}</strong> "
            f'<span style="opacity:0.7">({cluster.cluster_id})</span>'
            f"</div>",
            unsafe_allow_html=True,
        )
        if not cluster.turns:
            st.caption(
                "Cluster no encontrado. Suele ocurrir cuando los cluster IDs vienen "
                "de un clustering nuevo pero el resultado no incluye "
                "`clustering_result_file` (re-ejecuta el pipeline o enlaza el JSON de clustering)."
            )
            continue
        for turn in cluster.turns:
            speaker = turn.get("speaker", "?")
            text = turn.get("text", "")
            turn_id = turn.get("turn_id", "")
            speaker_label = str(speaker)
            if turn_id != "":
                speaker_label = f"{speaker_label} · turn {turn_id}"
            st.markdown(f"**{speaker_label}**")
            st.write(str(text))


def _section_outputs_by_id(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    section_outputs = payload.get("section_outputs")
    if not isinstance(section_outputs, list):
        return {}
    by_id: dict[str, dict[str, object]] = {}
    for section_output in section_outputs:
        if not isinstance(section_output, dict):
            continue
        section_id = section_output.get("section_id")
        if isinstance(section_id, str) and section_id.strip():
            by_id[section_id] = section_output
    return by_id


def _thinking_source_label(
    thinking_source: str | None,
    *,
    provider: str | None,
) -> str:
    if not thinking_source:
        return "Desconocida"
    if thinking_source == "message.reasoning":
        return "OpenAI: campo `message.reasoning`"
    if thinking_source == "message.reasoning_content":
        return "Reasoning estructurado (`message.reasoning_content`)"
    if thinking_source == "openai.responses.reasoning.summary":
        return "OpenAI Responses API: resumen de reasoning"
    if thinking_source.endswith(".content.thinking_tags"):
        provider_label = provider or "LLM"
        return f"{provider_label}: bloques think/thinking embebidos en el contenido"
    return thinking_source


def _reasoning_tokens_from_usage(llm_usage: object) -> int | None:
    return reasoning_tokens_from_usage(llm_usage)


def _format_timing_ms(value: object) -> str:
    if isinstance(value, int):
        return f"{value:,} ms"
    return "—"


def _timing_from_call_record(call_record: dict[str, object]) -> dict[str, object] | None:
    timing = call_record.get("llm_timing")
    if isinstance(timing, dict):
        return timing
    timing = call_record.get("timing")
    if isinstance(timing, dict):
        return timing
    return None


def _render_llm_timing_breakdown(call_record: dict[str, object]) -> None:
    timing = _timing_from_call_record(call_record)
    if timing is None:
        st.caption("Sin desglose de timing (re-ejecuta clustering).")
        return

    col_ttft, col_thinking, col_output, col_total = st.columns(4)
    col_ttft.metric(
        "TTFT",
        _format_timing_ms(timing.get("time_to_first_token_ms")),
    )
    col_thinking.metric(
        "Thinking time",
        _format_timing_ms(timing.get("thinking_time_ms")),
    )
    col_output.metric(
        "Output time",
        _format_timing_ms(timing.get("output_time_ms")),
    )
    col_total.metric(
        "Total stream",
        _format_timing_ms(timing.get("total_ms")),
    )

    if timing.get("estimated"):
        st.caption(
            "Thinking/output estimados por ratio de tokens (provider sin streaming)."
        )
    elif timing.get("streamed"):
        st.caption("Timing medido con streaming del provider.")


def _render_usage_token_breakdown(llm_usage: object) -> None:
    parsed = parse_token_usage(llm_usage)
    breakdown = output_token_breakdown_from_usage(llm_usage)

    col_in, col_reason, col_out = st.columns(3)
    if parsed is not None:
        col_in.metric("Input tokens", f"{parsed.input_tokens:,}")
    else:
        col_in.metric("Input tokens", "—")

    reasoning_tokens = breakdown.get("reasoning_tokens")
    if reasoning_tokens is not None:
        col_reason.metric("Reasoning tokens", f"{reasoning_tokens:,}")
    else:
        col_reason.metric("Reasoning tokens", "—")

    visible_output = breakdown.get("visible_output_tokens")
    total_output = breakdown.get("total_output_tokens")
    if visible_output is not None and (
        reasoning_tokens is None or visible_output != total_output
    ):
        col_out.metric("Output tokens", f"{visible_output:,}")
    elif total_output is not None:
        col_out.metric("Output tokens", f"{total_output:,}")
    else:
        col_out.metric("Output tokens", "—")


def _render_llm_call_thinking_content(
    *,
    payload: dict[str, object],
    call_label: str,
    call_record: dict[str, object],
) -> None:
    provider = payload.get("provider")
    provider_label = provider if isinstance(provider, str) else "—"
    model = payload.get("model")
    model_label = model if isinstance(model, str) else "—"
    thinking_source = call_record.get("thinking_source")
    thinking_source_label = _thinking_source_label(
        thinking_source if isinstance(thinking_source, str) else None,
        provider=provider_label if isinstance(provider, str) else None,
    )

    st.markdown(f"**{call_label}**")
    col_provider, col_source = st.columns(2)
    col_provider.caption(f"Provider/model: `{provider_label}` / `{model_label}`")
    col_source.caption(f"Fuente: {thinking_source_label}")

    _render_usage_token_breakdown(call_record.get("llm_usage"))
    _render_llm_timing_breakdown(call_record)

    thinking = call_record.get("thinking")
    if isinstance(thinking, str) and thinking.strip():
        st.text(thinking)
        return

    thinking_chars = call_record.get("thinking_chars")
    if isinstance(thinking_chars, int) and thinking_chars > 0:
        st.info(
            f"Hay thinking ({thinking_chars} caracteres) pero no se guardó el texto. "
            "Re-ejecuta clustering con `OUTPUT_DETAIL=full` o una versión reciente del harness."
        )
        return

    if _reasoning_tokens_from_usage(call_record.get("llm_usage")) is not None:
        st.caption(
            "El provider reportó reasoning tokens pero no hay texto exportado. "
            "Con Chat Completions el reasoning suele ser interno; en OpenAI usa "
            "reasoning_effort ≠ none (Responses API captura el resumen)."
        )
        return

    st.caption("Sin thinking para esta llamada.")


def _render_llm_call_thinking_button(
    *,
    payload: dict[str, object],
    call_label: str,
    call_record: dict[str, object],
    key_suffix: str,
) -> None:
    with st.popover(
        "Ver thinking",
        help=f"Razonamiento del modelo en {call_label}",
        key=f"clustering_thinking_{key_suffix}",
    ):
        _render_llm_call_thinking_content(
            payload=payload,
            call_label=call_label,
            call_record=call_record,
        )


def _render_section_thinking_content(
    *,
    payload: dict[str, object],
    section_id: str,
    heading: str,
    section_output: dict[str, object] | None,
) -> None:
    st.markdown(f"**{heading}** · `{section_id}`")
    if section_output is None:
        st.warning("Sin metadata de thinking para esta sección en el resultado.")
        return

    provider = payload.get("provider")
    provider_label = provider if isinstance(provider, str) else "—"
    model = payload.get("model")
    model_label = model if isinstance(model, str) else "—"
    thinking_source = section_output.get("thinking_source")
    thinking_source_label = _thinking_source_label(
        thinking_source if isinstance(thinking_source, str) else None,
        provider=provider_label if isinstance(provider, str) else None,
    )
    llm_usage = section_output.get("llm_usage")
    reasoning_tokens = _reasoning_tokens_from_usage(llm_usage)

    col_provider, col_source = st.columns(2)
    col_provider.caption(f"Provider/model: `{provider_label}` / `{model_label}`")
    col_source.caption(f"Fuente: {thinking_source_label}")
    if reasoning_tokens is not None:
        st.metric("Reasoning tokens (usage)", reasoning_tokens)

    thinking = section_output.get("thinking")
    if isinstance(thinking, str) and thinking.strip():
        st.text(thinking)
        return

    thinking_chars = section_output.get("thinking_chars")
    if isinstance(thinking_chars, int) and thinking_chars > 0:
        st.info(
            f"Hay thinking ({thinking_chars} caracteres) pero no se guardó el texto. "
            "Re-ejecuta generation con una versión reciente del harness."
        )
        return

    if reasoning_tokens is not None:
        st.caption(
            "OpenAI reportó reasoning tokens pero no hay texto exportado. "
            "Con Chat Completions el reasoning suele ser interno; re-ejecuta generation "
            "con thinking level ≠ none (el harness usa Responses API para capturar el resumen)."
        )
        return

    st.caption("Sin thinking para esta sección.")


def _render_section_thinking_button(
    *,
    payload: dict[str, object],
    section_id: str,
    heading: str,
    section_output: dict[str, object] | None,
    key_suffix: str,
) -> None:
    with st.popover(
        "Ver thinking",
        help="Razonamiento del modelo al generar esta sección",
        key=f"gen_thinking_{section_id}_{key_suffix}",
    ):
        _render_section_thinking_content(
            payload=payload,
            section_id=section_id,
            heading=str(heading),
            section_output=section_output,
        )


def _render_generation_section_actions(
    *,
    payload: dict[str, object],
    section_id: str,
    heading: str,
    cluster_ids: list[str],
    section_output: dict[str, object] | None,
    key_suffix: str,
) -> None:
    _, action_col = st.columns([4, 2])
    with action_col:
        turns_col, thinking_col = st.columns(2)
        with turns_col:
            if cluster_ids:
                _render_section_source_turns_button(
                    payload=payload,
                    section_id=section_id,
                    heading=str(heading),
                    cluster_ids=cluster_ids,
                    key_suffix=key_suffix,
                )
        with thinking_col:
            _render_section_thinking_button(
                payload=payload,
                section_id=section_id,
                heading=str(heading),
                section_output=section_output,
                key_suffix=key_suffix,
            )


def _render_compact_llm_call_metadata(call_record: dict[str, object]) -> None:
    usage = call_record.get("usage")
    request_params = call_record.get("request_params")
    if isinstance(usage, dict) and usage:
        st.caption("**usage**")
        st.json(usage)
    if isinstance(request_params, dict) and request_params:
        st.caption("**request_params**")
        st.json(request_params)


def _render_linked_evidence_audit(
    *,
    section_output: dict[str, object] | None,
    final_content: str,
    key_suffix: str,
    section_id: str,
    content_view_mode: str,
    show_evidence_ids: bool,
) -> None:
    if not is_two_step_section_output(section_output):
        return

    with st.expander("Auditoría linked evidence", expanded=False):
        if is_legacy_two_step_section(section_output):
            st.info(
                "Run legado sin artefactos de auditoría. "
                "Re-ejecuta con **Linked evidence (two-step)** para ver planner y renderer."
            )
            return

        if section_output is None:
            return

        planner_tab, renderer_tab = st.tabs(["Planner", "Renderer"])

        llm_responses = section_output.get("llm_responses")

        with planner_tab:
            raw_content = planner_raw_output(section_output)
            if raw_content.strip():
                st.code(raw_content)
            else:
                st.caption("Sin output del planner.")

        with renderer_tab:
            if final_content.strip():
                if content_view_mode == CONTENT_VIEW_SOURCE:
                    st.code(final_content, language="markdown")
                else:
                    display_content = display_generation_content(
                        final_content,
                        content_view_mode=content_view_mode,
                        show_evidence_ids=show_evidence_ids,
                    )
                    st.markdown(display_content)
                    cited = format_cited_evidence_ids_caption(final_content)
                    if cited:
                        st.caption(cited)
            else:
                st.caption("Sin contenido final.")

            renderer_call = resolve_llm_response_by_step(
                llm_responses,
                step=RENDERER_STEP,
            )
            if renderer_call is not None and content_view_mode == CONTENT_VIEW_APPLIED:
                raw_content = renderer_call.get("content")
                if (
                    isinstance(raw_content, str)
                    and raw_content.strip()
                    and raw_content.strip() != final_content.strip()
                ):
                    st.markdown("**Raw response**")
                    st.code(raw_content)
                _render_compact_llm_call_metadata(renderer_call)
            elif renderer_call is not None:
                _render_compact_llm_call_metadata(renderer_call)


def _render_generation_section_body(
    *,
    payload: dict[str, object],
    section: dict[str, object],
    section_index: int,
    section_outputs_by_id: dict[str, dict[str, object]],
    key_suffix: str,
    content_view_mode: str,
    show_evidence_ids: bool,
    document_wrapper: bool = False,
) -> None:
    section_id = str(section.get("section_id", f"section_{section_index}"))
    heading = section.get("heading", section_id)
    content = section.get("content", "")
    cluster_ids_raw = section.get("cluster_ids", [])
    cluster_ids = (
        [str(cluster_id) for cluster_id in cluster_ids_raw]
        if isinstance(cluster_ids_raw, list)
        else []
    )
    section_output = section_outputs_by_id.get(section_id)
    content_text = content if isinstance(content, str) else ""

    if document_wrapper and (not content_text.strip()):
        return

    _render_generation_section_actions(
        payload=payload,
        section_id=section_id,
        heading=str(heading),
        cluster_ids=cluster_ids,
        section_output=section_output,
        key_suffix=key_suffix,
    )

    if content_text.strip():
        if content_view_mode == CONTENT_VIEW_SOURCE:
            st.code(content_text, language="markdown")
        else:
            display_content = display_generation_content(
                content_text,
                content_view_mode=content_view_mode,
                show_evidence_ids=show_evidence_ids,
            )
            st.markdown(display_content)
    elif not document_wrapper:
        st.caption("*(vacío)*")

    _render_linked_evidence_audit(
        section_output=section_output,
        final_content=content_text,
        key_suffix=f"{key_suffix}_{section_id}",
        section_id=section_id,
        content_view_mode=content_view_mode,
        show_evidence_ids=show_evidence_ids,
    )

    if not document_wrapper:
        st.markdown("")


def _render_generation_document_sections(
    payload: dict[str, object],
    *,
    key_suffix: str,
    document_wrapper: bool = False,
) -> None:
    session_result = payload.get("generation_session_result")
    if not isinstance(session_result, dict):
        return

    sections = session_result.get("sections")
    if not isinstance(sections, list):
        return

    section_outputs_by_id = _section_outputs_by_id(payload)
    has_two_step_sections = any(
        is_two_step_section_output(section_outputs_by_id.get(str(section.get("section_id", ""))))
        for section in sections
        if isinstance(section, dict)
    )

    content_view_mode = st.radio(
        "Vista del contenido",
        options=[CONTENT_VIEW_APPLIED, CONTENT_VIEW_SOURCE],
        index=0,
        horizontal=True,
        key=f"content_view_mode_{key_suffix}",
        help=(
            "Markdown aplicado renderiza el documento; "
            "Markdown fuente muestra el string persistido tal cual."
        ),
    )

    show_evidence_ids = False
    if has_two_step_sections and content_view_mode == CONTENT_VIEW_APPLIED:
        show_evidence_ids = st.checkbox(
            "Mostrar IDs de evidencia",
            value=False,
            key=f"show_evidence_ids_{key_suffix}",
            help="Muestra los markers inline {{e:...}} en el documento generado.",
        )

    if document_wrapper:
        st.markdown(
            '<div style="max-width:860px;margin:0 auto">',
            unsafe_allow_html=True,
        )

    for index, section in enumerate(sections):
        if not isinstance(section, dict):
            continue
        _render_generation_section_body(
            payload=payload,
            section=section,
            section_index=index,
            section_outputs_by_id=section_outputs_by_id,
            key_suffix=key_suffix,
            content_view_mode=content_view_mode,
            show_evidence_ids=show_evidence_ids,
            document_wrapper=document_wrapper,
        )

    if document_wrapper:
        st.markdown("</div>", unsafe_allow_html=True)


def _render_section_source_turns_button(
    *,
    payload: dict[str, object],
    section_id: str,
    heading: str,
    cluster_ids: list[str],
    key_suffix: str,
) -> None:
    with st.popover(
        "Ver turnos fuente",
        help="Turnos de los clusters usados para generar esta sección",
        key=f"gen_turns_{section_id}_{key_suffix}",
    ):
        clusters = cluster_turns_from_generation_payload(payload, cluster_ids)
        _render_section_source_turns_content(
            heading=str(heading),
            section_id=section_id,
            clusters=clusters,
        )


def _render_dropped_turns(decisions: list[dict[str, object]]) -> None:
    dropped = [
        decision
        for decision in decisions
        if isinstance(decision, dict) and decision.get("keep") == 0
    ]
    if not dropped:
        return

    with st.expander(f"Turnos descartados ({len(dropped)})", expanded=True):
        for decision in dropped:
            speaker = decision.get("speaker", "?")
            text = decision.get("text", "")
            turn_id = decision.get("turn_id", "")
            st.markdown(
                '<div style="border-left:3px solid #F44336;'
                'padding:2px 10px;margin-top:8px">',
                unsafe_allow_html=True,
            )
            speaker_label = str(speaker)
            if turn_id != "":
                speaker_label = f"{speaker_label} · turn {turn_id}"
            st.markdown(f"**{speaker_label}**")
            st.write(str(text))


def render_filtering_result(payload: dict[str, object]) -> None:
    filtering_result = payload.get("filtering_result")
    if not isinstance(filtering_result, dict):
        st.warning("Sin filtering_result en el payload.")
        render_json_expander(payload)
        return

    drop_turn_ids = filtering_result.get("drop_turn_ids", [])
    keep_count = filtering_result.get("keep_count")
    drop_count = filtering_result.get("drop_count")
    total = payload.get("turn_count")

    cols = st.columns(3)
    cols[0].metric(
        "Turnos conservados",
        keep_count if keep_count is not None else "—",
    )
    cols[1].metric(
        "Turnos descartados",
        drop_count if drop_count is not None else "—",
        delta=None if drop_count is None else f"-{drop_count}" if drop_count else None,
        delta_color="inverse" if drop_count else "off",
    )
    cols[2].metric("Total", total if total is not None else "—")

    decisions = filtering_result.get("decisions")
    if isinstance(decisions, list) and decisions:
        _render_dropped_turns(decisions)
        with st.expander(f"Decisiones ({len(decisions)})"):
            st.dataframe(decisions, use_container_width=True)
    elif not (isinstance(drop_turn_ids, list) and drop_turn_ids):
        st.success("No se descartaron turnos.")

    render_json_expander(payload)


def render_clustering_result(payload: dict[str, object]) -> None:
    clustering_result = payload.get("clustering_result")
    if not isinstance(clustering_result, dict):
        st.warning("Sin clustering_result en el payload.")
        render_json_expander(payload)
        return

    clusters = clustering_result.get("clusters")
    if not isinstance(clusters, list):
        st.warning("Sin clusters en el resultado.")
        render_json_expander(payload)
        return

    unassigned = clustering_result.get("unassigned_turn_ids")
    turn_coverage = payload.get("turn_coverage")
    missing_turn_ids: list[int] = []
    if isinstance(turn_coverage, dict):
        raw_missing = turn_coverage.get("missing_turn_ids")
        if isinstance(raw_missing, list):
            missing_turn_ids = [int(turn_id) for turn_id in raw_missing]

    col_n, col_u, col_m = st.columns(3)
    col_n.metric("Clusters", len(clusters))
    col_u.metric(
        "Sin asignar",
        len(unassigned) if isinstance(unassigned, list) else 0,
        delta_color="inverse",
    )
    col_m.metric(
        "Missing",
        len(missing_turn_ids),
        delta_color="inverse",
    )
    if isinstance(unassigned, list) and unassigned:
        st.warning(f"Turnos sin asignar: `{unassigned}`")
    if missing_turn_ids:
        st.error(f"Turnos missing (no cubiertos por clustering): `{missing_turn_ids}`")

    initial_call: dict[str, object] = {
        "thinking": payload.get("thinking"),
        "thinking_source": payload.get("thinking_source"),
        "thinking_chars": payload.get("thinking_chars"),
        "llm_usage": payload.get("llm_usage"),
        "llm_timing": payload.get("llm_timing"),
    }
    has_initial_thinking_metadata = any(
        initial_call.get(key) is not None
        for key in (
            "thinking",
            "thinking_source",
            "thinking_chars",
            "llm_usage",
            "llm_timing",
        )
    )
    if has_initial_thinking_metadata:
        st.markdown("**Thinking, tokens & timing**")
        col_tokens, col_thinking = st.columns([3, 1])
        with col_tokens:
            _render_usage_token_breakdown(initial_call.get("llm_usage"))
            _render_llm_timing_breakdown(initial_call)
        with col_thinking:
            _render_llm_call_thinking_button(
                payload=payload,
                call_label="Clustering · inicial",
                call_record=initial_call,
                key_suffix="initial",
            )

    repair_passes = payload.get("repair_passes")
    if isinstance(repair_passes, list) and repair_passes:
        with st.expander(f"Repair passes ({len(repair_passes)})"):
            summary_rows: list[dict[str, object]] = []
            for repair_pass in repair_passes:
                if not isinstance(repair_pass, dict):
                    continue
                pass_index = repair_pass.get("pass_index")
                call_label = (
                    f"Clustering · repair {pass_index}"
                    if pass_index is not None
                    else "Clustering · repair"
                )
                pass_key = (
                    f"repair_{pass_index}"
                    if pass_index is not None
                    else f"repair_{len(summary_rows)}"
                )
                col_tokens, col_thinking = st.columns([3, 1])
                with col_tokens:
                    _render_usage_token_breakdown(repair_pass.get("llm_usage"))
                    _render_llm_timing_breakdown(repair_pass)
                with col_thinking:
                    _render_llm_call_thinking_button(
                        payload=payload,
                        call_label=call_label,
                        call_record=repair_pass,
                        key_suffix=pass_key,
                    )
                summary_rows.append(
                    {
                        key: value
                        for key, value in repair_pass.items()
                        if key not in {"thinking", "llm_usage"}
                    }
                )
            if summary_rows:
                st.dataframe(summary_rows, use_container_width=True, hide_index=True)

    for i, cluster in enumerate(clusters):
        if not isinstance(cluster, dict):
            continue
        topic_label = cluster.get("topic_label", f"cluster_{i}")
        turns = cluster.get("turns", [])
        turn_count = len(turns) if isinstance(turns, list) else 0
        color = _cluster_color(i)
        with st.expander(
            f"{'●'} {topic_label}  ({turn_count} turnos)",
            expanded=False,
        ):
            st.markdown(
                f'<div style="width:100%;height:3px;background:{color};'
                f'border-radius:2px;margin-bottom:8px"></div>',
                unsafe_allow_html=True,
            )
            if isinstance(turns, list) and turns:
                st.dataframe(turns, use_container_width=True)
            else:
                st.caption("(sin turnos)")

    render_json_expander(payload)


def render_classification_result(payload: dict[str, object]) -> None:
    session_result = payload.get("classification_session_result")
    if not isinstance(session_result, dict):
        st.warning("Sin classification_session_result en el payload.")
        render_json_expander(payload)
        return

    assignments = session_result.get("assignments")
    if isinstance(assignments, list):
        rows = []
        for item in assignments:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "cluster_id": item.get("cluster_id"),
                    "section_ids": ", ".join(item.get("section_ids", []))
                    if isinstance(item.get("section_ids"), list)
                    else "",
                }
            )
        if rows:
            st.metric("Asignaciones", len(rows))
            st.dataframe(rows, use_container_width=True)

    batch_plan = payload.get("batch_plan")
    if isinstance(batch_plan, dict):
        with st.expander("Batch plan"):
            st.json(batch_plan)

    batch_outputs = payload.get("batch_outputs")
    if isinstance(batch_outputs, list):
        for batch in batch_outputs:
            if not isinstance(batch, dict):
                continue
            thinking = batch.get("thinking")
            if isinstance(thinking, str) and thinking.strip():
                with st.expander(f"Thinking — batch {batch.get('batch_index', '?')}"):
                    st.text(thinking)

    render_json_expander(payload)


def render_generation_result(payload: dict[str, object]) -> None:
    session_result = payload.get("generation_session_result")
    if not isinstance(session_result, dict):
        st.warning("Sin generation_session_result en el payload.")
        render_json_expander(payload)
        return

    key_suffix = str(abs(hash(json.dumps(payload, sort_keys=True, default=str))))
    sections = session_result.get("sections")
    if isinstance(sections, list):
        filled = [
            section
            for section in sections
            if isinstance(section, dict) and str(section.get("content", "")).strip()
        ]
        st.metric("Secciones generadas", len(filled))
        st.divider()

    _render_generation_document_sections(
        payload,
        key_suffix=key_suffix,
        document_wrapper=False,
    )

    skipped = session_result.get("skipped_sections")
    if isinstance(skipped, list) and skipped:
        with st.expander(f"Secciones omitidas ({len(skipped)})"):
            for item in skipped:
                if isinstance(item, dict):
                    st.write(f"- `{item.get('section_id')}` {item.get('heading', '')}")

    render_json_expander(payload)


def render_e2e_document(generation_record: dict[str, object]) -> None:
    session_result = generation_record.get("generation_session_result")
    if not isinstance(session_result, dict):
        return
    sections = session_result.get("sections")
    if not isinstance(sections, list):
        return

    key_suffix = str(
        abs(hash(json.dumps(generation_record, sort_keys=True, default=str)))
    )
    _render_generation_document_sections(
        generation_record,
        key_suffix=f"e2e_{key_suffix}",
        document_wrapper=True,
    )


def _id_text_rows(
    items_raw: object,
    *,
    truncate_at: int | None = 120,
) -> list[dict[str, object]]:
    if not isinstance(items_raw, list) or not items_raw:
        return []
    rows: list[dict[str, object]] = []
    for item in items_raw:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", ""))
        if truncate_at is not None and len(text) > truncate_at:
            text = text[: truncate_at - 3] + "..."
        rows.append({"id": item.get("id"), "text": text})
    return rows


def _render_id_text_table(
    items_raw: object,
    *,
    title: str,
    truncate_at: int | None = 120,
    empty_message: str = "Sin items.",
) -> None:
    rows = _id_text_rows(items_raw, truncate_at=truncate_at)
    st.markdown(f"**{title}**")
    if not rows:
        st.info(empty_message)
        return
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_doctor_items_table(items_raw: object) -> None:
    _render_id_text_table(items_raw, title="Items", truncate_at=120)


def _normalize_spans_list(spans_raw: object) -> list[dict[str, object]]:
    if not isinstance(spans_raw, list):
        return []
    return [span for span in spans_raw if isinstance(span, dict)]


def _spans_by_id(spans_raw: object) -> dict[str, dict[str, object]]:
    lookup: dict[str, dict[str, object]] = {}
    for span in _normalize_spans_list(spans_raw):
        span_id = span.get("id")
        if isinstance(span_id, str) and span_id:
            lookup[span_id] = span
    return lookup


def _spans_for_ids(
    span_ids: object,
    spans_by_id: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    if not isinstance(span_ids, list):
        return []
    spans: list[dict[str, object]] = []
    for span_id in span_ids:
        if not isinstance(span_id, str):
            continue
        span = spans_by_id.get(span_id)
        if span is not None:
            spans.append(span)
    return spans


def _dropped_spans_from_payload(payload: dict[str, object]) -> list[dict[str, object]]:
    filter_result = payload.get("filter_spans_result")
    drop_ids: list[str] = []
    if isinstance(filter_result, dict):
        raw_drop_ids = filter_result.get("drop_ids")
        if isinstance(raw_drop_ids, list):
            drop_ids = [str(span_id) for span_id in raw_drop_ids if span_id]
    if drop_ids:
        pool_for_drops = payload.get("document_spans")
        if not isinstance(pool_for_drops, list) or not pool_for_drops:
            pool_for_drops = payload.get("span_pool")
        return _spans_for_ids(drop_ids, _spans_by_id(pool_for_drops))

    span_pool = _normalize_spans_list(payload.get("span_pool"))
    kept_ids = {
        str(span.get("id"))
        for span in _normalize_spans_list(payload.get("filtered_spans"))
        if span.get("id")
    }
    return [
        span
        for span in span_pool
        if str(span.get("id", "")) and str(span.get("id")) not in kept_ids
    ]


def _render_spans_table(spans_raw: object) -> None:
    if not isinstance(spans_raw, list) or not spans_raw:
        st.info("Sin spans.")
        return
    rows: list[dict[str, object]] = []
    for span in spans_raw:
        if not isinstance(span, dict):
            continue
        text = str(span.get("text", ""))
        if len(text) > 100:
            text = text[:97] + "..."
        rows.append(
            {
                "id": span.get("id"),
                "doc": span.get("doc"),
                "kind": span.get("kind"),
                "text": text,
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_clusters_table(clusters_raw: object) -> None:
    if not isinstance(clusters_raw, list) or not clusters_raw:
        st.info("Sin clusters.")
        return
    rows: list[dict[str, object]] = []
    for cluster in clusters_raw:
        if not isinstance(cluster, dict):
            continue
        span_ids = cluster.get("span_ids", [])
        rows.append(
            {
                "id": cluster.get("id"),
                "title": cluster.get("title"),
                "span_count": len(span_ids) if isinstance(span_ids, list) else 0,
                "span_ids": ", ".join(span_ids) if isinstance(span_ids, list) else "",
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_context_triage_result(payload: dict[str, object]) -> None:
    doctor_items = payload.get("doctor_items")
    triage_result = payload.get("triage_result")
    is_pasted = payload.get("is_pasted")

    content_ids: list[object] = []
    drop_ids: list[object] = []
    directives: list[object] = []
    if isinstance(triage_result, dict):
        raw_content_ids = triage_result.get("content_ids")
        raw_drop_ids = triage_result.get("drop_ids")
        raw_directives = triage_result.get("directives")
        if isinstance(raw_content_ids, list):
            content_ids = raw_content_ids
        if isinstance(raw_drop_ids, list):
            drop_ids = raw_drop_ids
        if isinstance(raw_directives, list):
            directives = raw_directives

    disposition_rows = triage_item_disposition_rows(
        doctor_items,
        content_ids=content_ids,
        drop_ids=drop_ids,
    )
    content_count = sum(
        1
        for row in disposition_rows
        if row["disposición"]
        in (DISPOSITION_CONTENT, DISPOSITION_DROPPED_AND_CONTENT)
    )
    dropped_count = sum(
        1
        for row in disposition_rows
        if row["disposición"]
        in (DISPOSITION_DROPPED, DISPOSITION_DROPPED_AND_CONTENT)
    )
    unclassified_count = sum(
        1
        for row in disposition_rows
        if row["disposición"] == DISPOSITION_UNCLASSIFIED
    )

    col_split, col_pasted, col_content, col_dropped = st.columns(4)
    col_split.metric("Items tras split", len(disposition_rows))
    if isinstance(is_pasted, bool):
        col_pasted.metric("is_pasted", "sí" if is_pasted else "no")
    else:
        col_pasted.metric("is_pasted", "—")
    col_content.metric("Contenido clínico", content_count)
    col_dropped.metric("Descartados", dropped_count)

    st.markdown("**Qué pasó con cada fragmento**")
    if disposition_rows:
        st.dataframe(disposition_rows, use_container_width=True, hide_index=True)
        if dropped_count and directives:
            st.caption(
                "Un item **descartado** suele ser solo instrucción (p. ej. "
                "«no uses la epicrisis»). Eso no va a `content_ids`, pero puede "
                "generar una **directiva** sobre documentos abajo."
            )
        elif dropped_count and not directives:
            st.caption(
                "Los items **descartados** no siguen como contenido clínico "
                "(`content_ids` vacío para esos IDs)."
            )
        if unclassified_count:
            st.warning(
                f"{unclassified_count} item(s) no aparecen ni en content_ids "
                "ni en drop_ids."
            )
    else:
        st.info("Sin `doctor_items` en el resultado.")

    st.markdown("**Directivas sobre documentos / contexto**")
    st.caption(
        "Aplican a PDFs y fuentes externas en pasos posteriores "
        "(filter_spans, adapter). No usan los mismos IDs que los fragmentos "
        "de la nota."
    )
    if directives:
        st.dataframe(directives, use_container_width=True, hide_index=True)
    else:
        st.caption("Sin directivas.")

    render_json_expander(payload)


def render_context_filter_spans_result(payload: dict[str, object]) -> None:
    from ui.filter_spans_audit import build_context_filter_spans_view

    view = build_context_filter_spans_view(payload)

    metric_cols = st.columns(4)
    metric_cols[0].metric("Descartados por filter_spans", view["filter_drop_count"])
    metric_cols[1].metric("Conservados tras filter_spans", view["filter_kept_count"])
    metric_cols[2].metric("Descartados por directives", view["directive_drop_count"])
    metric_cols[3].metric("Conservados tras directives", view["directive_kept_count"])

    if view["show_directive_no_applicable_caption"]:
        st.caption("No hubo directives documentales aplicables.")

    st.caption(
        "`filter_spans` aplica filtro clínico general. "
        "`document_directive_filter` aplica instrucciones documentales del triage. "
        "La nota del médico no pasa por ninguno de los dos."
    )

    approved_note_spans = view["approved_note_spans"]
    if approved_note_spans:
        st.markdown("**Nota del médico (sin re-filtrar)**")
        _render_spans_table(approved_note_spans)

    document_input_spans = view["document_input_spans"]
    if document_input_spans:
        st.markdown("**Pool de documentos (entrada a filter_spans)**")
        _render_spans_table(document_input_spans)

    st.markdown("**Descartados por filter_spans**")
    _render_spans_table(view["filter_dropped_spans"])

    st.markdown("**Conservados tras filter_spans / entrada a directives**")
    _render_spans_table(view["after_filter_spans"])

    st.markdown("**Descartados por directives**")
    _render_spans_table(view["directive_dropped_spans"])

    st.markdown("**Documentos finales tras directives**")
    _render_spans_table(view["after_directive_spans"])

    st.markdown("**Spans tras merge (nota + documentos finales)**")
    _render_spans_table(view["merged_spans"])
    render_json_expander(payload)


def render_context_cluster_spans_result(payload: dict[str, object]) -> None:
    missing_span_ids = payload.get("missing_span_ids")
    missing_spans = payload.get("missing_spans")
    if isinstance(missing_span_ids, list) and missing_span_ids:
        st.warning(
            "Spans no asignados a ningún cluster: "
            + ", ".join(f"`{span_id}`" for span_id in missing_span_ids)
        )
    if isinstance(missing_spans, list) and missing_spans:
        st.markdown("**Spans no clusterizados**")
        _render_spans_table(missing_spans)

    cluster_result = payload.get("cluster_spans_result")
    clusters_raw: object = None
    if isinstance(cluster_result, dict):
        cluster_count = cluster_result.get("cluster_count")
        if isinstance(cluster_count, int):
            st.metric("Clusters", cluster_count)
        clusters_raw = cluster_result.get("clusters")
        st.markdown("**Resumen de clusters**")
        _render_clusters_table(clusters_raw)

    spans_by_id = _spans_by_id(payload.get("filtered_spans"))
    if isinstance(clusters_raw, list) and clusters_raw:
        st.markdown("**Contenido por cluster**")
        for cluster in clusters_raw:
            if not isinstance(cluster, dict):
                continue
            cluster_id = str(cluster.get("id", "?"))
            title = cluster.get("title")
            span_ids = cluster.get("span_ids", [])
            span_count = len(span_ids) if isinstance(span_ids, list) else 0
            label = f"`{cluster_id}`"
            if isinstance(title, str) and title.strip():
                label += f" — {title}"
            label += f" ({span_count} spans)"
            with st.expander(label, expanded=False):
                cluster_spans = _spans_for_ids(span_ids, spans_by_id)
                if not cluster_spans and span_count > 0:
                    st.warning("No se encontró el texto de los spans en el payload.")
                _render_spans_table(cluster_spans)
    render_json_expander(payload)


def render_context_classify_clusters_result(payload: dict[str, object]) -> None:
    classify_result = payload.get("classify_clusters_result")
    if isinstance(classify_result, dict):
        assignments = classify_result.get("assignments")
        if isinstance(assignments, list) and assignments:
            st.dataframe(assignments, use_container_width=True, hide_index=True)
        else:
            st.info("Sin assignments.")
    render_json_expander(payload)


def render_context_section_adapter_result(payload: dict[str, object]) -> None:
    adapter_jobs = payload.get("adapter_jobs")
    if isinstance(adapter_jobs, dict) and adapter_jobs:
        rows: list[dict[str, object]] = []
        for section_id, cluster_ids in sorted(adapter_jobs.items()):
            ids = (
                [str(cluster_id) for cluster_id in cluster_ids]
                if isinstance(cluster_ids, list)
                else []
            )
            rows.append(
                {
                    "section_id": section_id,
                    "cluster_count": len(ids),
                    "cluster_ids": ", ".join(ids),
                }
            )
        st.markdown("**Jobs por sección**")
        st.dataframe(rows, use_container_width=True, hide_index=True)

    section_context = payload.get("section_context")
    if isinstance(section_context, dict) and section_context:
        st.markdown("**section_context**")
        for section_id, content in section_context.items():
            text = str(content)
            label = f"`{section_id}`"
            if text.strip():
                label += f" · {len(text)} chars"
            with st.expander(label, expanded=False):
                st.markdown(text or "_(vacío)_")
    else:
        st.info("section_context vacío.")
    render_json_expander(payload)


def _pipeline_has_doctor_note(payload: dict[str, object]) -> bool:
    has_note = payload.get("has_doctor_note")
    if isinstance(has_note, bool):
        return has_note
    include_doctor = payload.get("include_doctor_note")
    if isinstance(include_doctor, bool):
        return include_doctor
    doctor_items = payload.get("doctor_items")
    return isinstance(doctor_items, list) and len(doctor_items) > 0


def _pipeline_source_caption(payload: dict[str, object]) -> str | None:
    has_note = payload.get("has_doctor_note")
    has_pdf = payload.get("has_document_pdf")
    include_doctor = payload.get("include_doctor_note")
    include_docs = payload.get("include_documents")

    if isinstance(has_note, bool) or isinstance(has_pdf, bool):
        return (
            "Fuentes: "
            f"nota del médico={'sí' if has_note else 'no'} · "
            f"documento PDF={'sí' if has_pdf else 'no'}"
        )
    if isinstance(include_doctor, bool) or isinstance(include_docs, bool):
        return (
            "Fuentes: "
            f"nota del médico={'sí' if include_doctor else 'no'} · "
            f"documentos previos={'sí' if include_docs else 'no'}"
        )
    return None


def _derive_filter_spans_result(payload: dict[str, object]) -> dict[str, object] | None:
    existing = payload.get("filter_spans_result")
    if isinstance(existing, dict):
        return existing
    span_pool = payload.get("span_pool")
    filtered_spans = payload.get("filtered_spans")
    if not isinstance(span_pool, list) or not isinstance(filtered_spans, list):
        return None
    kept_ids = {
        str(span.get("id"))
        for span in filtered_spans
        if isinstance(span, dict) and span.get("id")
    }
    drop_ids = [
        str(span.get("id"))
        for span in span_pool
        if isinstance(span, dict) and span.get("id") and str(span.get("id")) not in kept_ids
    ]
    return {
        "drop_ids": drop_ids,
        "drop_count": len(drop_ids),
        "kept_span_count": len(kept_ids),
    }


def _filter_spans_step_payload(payload: dict[str, object]) -> dict[str, object]:
    step_payload = dict(payload)
    filter_result = _derive_filter_spans_result(payload)
    if filter_result is not None:
        step_payload["filter_spans_result"] = filter_result
    return step_payload


PIPELINE_LLM_STEP_ORDER = (
    "triage",
    "filter_spans",
    "cluster_spans",
    "classify_clusters",
    "section_adapter",
)


def _pipeline_step_executed(payload: dict[str, object], step: str) -> bool:
    stopped_after = payload.get("stopped_after_step")
    if not isinstance(stopped_after, str):
        return True
    if step not in PIPELINE_LLM_STEP_ORDER:
        return True
    return PIPELINE_LLM_STEP_ORDER.index(step) <= PIPELINE_LLM_STEP_ORDER.index(
        stopped_after
    )


def _render_pipeline_partial_banner(payload: dict[str, object]) -> None:
    pipeline_error = payload.get("pipeline_error")
    if not isinstance(pipeline_error, str) or not pipeline_error:
        return
    stopped_after = payload.get("stopped_after_step")
    stopped_label = stopped_after if isinstance(stopped_after, str) else "?"
    st.warning(
        f"Pipeline parcial: se detuvo tras **{stopped_label}**. "
        f"Los pasos posteriores no se ejecutaron. "
        f"Motivo: `{pipeline_error}`"
    )


def _render_pipeline_step_tab(
    payload: dict[str, object],
    *,
    step: str,
    render_fn: object,
) -> None:
    if not _pipeline_step_executed(payload, step):
        st.info("Paso no ejecutado: el pipeline se detuvo antes de llegar aquí.")
        return
    if callable(render_fn):
        render_fn()
    pipeline_error = payload.get("pipeline_error")
    stopped_after = payload.get("stopped_after_step")
    if (
        isinstance(pipeline_error, str)
        and pipeline_error
        and stopped_after == step
        and step in {"filter_spans", "cluster_spans"}
    ):
        st.error(pipeline_error)


def _render_pipeline_summary(payload: dict[str, object]) -> None:
    _render_pipeline_partial_banner(payload)
    source_caption = _pipeline_source_caption(payload)
    if source_caption:
        st.caption(source_caption)

    col_session, col_template, col_pasted = st.columns(3)
    session_id = payload.get("session_id")
    if isinstance(session_id, str) and session_id:
        col_session.metric("Session", session_id)
    template_id = payload.get("template_id")
    if isinstance(template_id, str) and template_id:
        col_template.metric("Template", template_id)
    is_pasted = payload.get("is_pasted")
    if isinstance(is_pasted, bool):
        col_pasted.metric("is_pasted", "sí" if is_pasted else "no")

    span_pool = payload.get("span_pool")
    filtered_spans = payload.get("filtered_spans")
    cluster_result = payload.get("cluster_spans_result")
    section_context = payload.get("section_context")

    col_pool, col_filtered, col_clusters, col_sections = st.columns(4)
    if isinstance(span_pool, list):
        col_pool.metric("Span pool", len(span_pool))
    if isinstance(filtered_spans, list):
        col_filtered.metric("Tras filter", len(filtered_spans))
    if isinstance(cluster_result, dict):
        cluster_count = cluster_result.get("cluster_count")
        if isinstance(cluster_count, int):
            col_clusters.metric("Clusters", cluster_count)
    if isinstance(section_context, dict):
        col_sections.metric("Secciones", len(section_context))

    encounter_date = payload.get("encounter_date")
    document_date = payload.get("document_date")
    if isinstance(encounter_date, str) and encounter_date:
        st.caption(f"Fecha consulta: {encounter_date}")
    if isinstance(document_date, str) and document_date:
        st.caption(f"Fecha documento: {document_date}")

    if not _pipeline_has_doctor_note(payload):
        st.info("Triage omitido: no hubo nota del médico en esta ejecución.")


def _render_llm_calls_table(llm_calls_raw: object) -> None:
    if not isinstance(llm_calls_raw, list) or not llm_calls_raw:
        st.info("Sin llamadas LLM registradas.")
        return
    rows: list[dict[str, object]] = []
    for call in llm_calls_raw:
        if not isinstance(call, dict):
            continue
        usage = call.get("llm_usage")
        total_tokens: object = None
        if isinstance(usage, dict):
            total_tokens = usage.get("total_tokens")
        rows.append(
            {
                "paso": call.get("label"),
                "provider": call.get("provider"),
                "model": call.get("model"),
                "total_tokens": total_tokens,
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_context_pipeline_result(payload: dict[str, object]) -> None:
    _render_pipeline_summary(payload)

    tab_labels = ["Resumen"]
    if _pipeline_has_doctor_note(payload):
        tab_labels.append("Triage")
    tab_labels.extend(
        [
            "Span pool",
            "Filter",
            "Cluster",
            "Classify",
            "Adapter",
            "LLM calls",
        ]
    )
    tabs = st.tabs(tab_labels)
    tab_index = 0

    with tabs[tab_index]:
        st.markdown("**Metadatos de ejecución**")
        meta_rows: list[dict[str, object]] = []
        for key in (
            "run_mode",
            "pipeline_status",
            "stopped_after_step",
            "pipeline_error",
            "case_id",
            "session_id",
            "template_id",
            "document_id",
            "encounter_date",
            "document_date",
            "provider",
            "model",
            "output_path",
        ):
            value = payload.get(key)
            if value is not None:
                meta_rows.append({"campo": key, "valor": value})
        if meta_rows:
            st.dataframe(meta_rows, use_container_width=True, hide_index=True)
        render_json_expander(payload, title="JSON completo del pipeline")
    tab_index += 1

    if _pipeline_has_doctor_note(payload):
        with tabs[tab_index]:
            _render_pipeline_step_tab(
                payload,
                step="triage",
                render_fn=lambda: render_context_triage_result(payload),
            )
        tab_index += 1

    with tabs[tab_index]:
        st.markdown("**Spans antes de filtrar**")
        _render_spans_table(payload.get("span_pool"))
        render_json_expander(
            {"span_pool": payload.get("span_pool", [])},
            title="JSON span pool",
        )
    tab_index += 1

    with tabs[tab_index]:
        _render_pipeline_step_tab(
            payload,
            step="filter_spans",
            render_fn=lambda: render_context_filter_spans_result(
                _filter_spans_step_payload(payload)
            ),
        )
    tab_index += 1

    with tabs[tab_index]:
        _render_pipeline_step_tab(
            payload,
            step="cluster_spans",
            render_fn=lambda: render_context_cluster_spans_result(payload),
        )
    tab_index += 1

    with tabs[tab_index]:
        _render_pipeline_step_tab(
            payload,
            step="classify_clusters",
            render_fn=lambda: render_context_classify_clusters_result(payload),
        )
    tab_index += 1

    with tabs[tab_index]:
        _render_pipeline_step_tab(
            payload,
            step="section_adapter",
            render_fn=lambda: render_context_section_adapter_result(payload),
        )
    tab_index += 1

    with tabs[tab_index]:
        _render_llm_calls_table(payload.get("llm_calls"))


def render_step_result(step: str, payload: dict[str, object]) -> None:
    render_step_latency(step, payload)
    if step == "filtering":
        render_filtering_result(payload)
    elif step == "clustering":
        render_clustering_result(payload)
    elif step == "classification":
        render_classification_result(payload)
    elif step == "generation":
        render_generation_result(payload)
    elif step == "context_triage":
        render_context_triage_result(payload)
    elif step == "context_filter_spans":
        render_context_filter_spans_result(payload)
    elif step == "context_cluster_spans":
        render_context_cluster_spans_result(payload)
    elif step == "context_classify_clusters":
        render_context_classify_clusters_result(payload)
    elif step == "context_section_adapter":
        render_context_section_adapter_result(payload)
    elif step == "context_pipeline":
        render_context_pipeline_result(payload)
    elif step == "context_ad_hoc_pipeline":
        render_context_pipeline_result(payload)
    else:
        render_json_expander(payload)
