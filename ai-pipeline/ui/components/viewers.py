from __future__ import annotations

import json

import streamlit as st

from common.llm_response import (
    output_token_breakdown_from_usage,
    reasoning_tokens_from_usage,
)
from common.usage_cost import parse_token_usage
from ui.cluster_lookup import ClusterTurnsView, cluster_turns_from_generation_payload
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
    section_outputs_by_id = _section_outputs_by_id(payload)

    sections = session_result.get("sections")
    if isinstance(sections, list):
        filled = [
            section
            for section in sections
            if isinstance(section, dict) and str(section.get("content", "")).strip()
        ]
        st.metric("Secciones generadas", len(filled))
        st.divider()
        for i, section in enumerate(sections):
            if not isinstance(section, dict):
                continue
            section_id = str(section.get("section_id", f"section_{i}"))
            heading = section.get("heading", section_id)
            content = section.get("content", "")
            cluster_ids_raw = section.get("cluster_ids", [])
            cluster_ids = (
                [str(cluster_id) for cluster_id in cluster_ids_raw]
                if isinstance(cluster_ids_raw, list)
                else []
            )

            _render_generation_section_actions(
                payload=payload,
                section_id=section_id,
                heading=str(heading),
                cluster_ids=cluster_ids,
                section_output=section_outputs_by_id.get(section_id),
                key_suffix=key_suffix,
            )

            if isinstance(content, str) and content.strip():
                st.markdown(content)
            else:
                st.caption("*(vacío)*")
            st.markdown("")

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
    section_outputs_by_id = _section_outputs_by_id(generation_record)

    st.markdown(
        '<div style="max-width:860px;margin:0 auto">',
        unsafe_allow_html=True,
    )
    for i, section in enumerate(sections):
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("section_id", f"section_{i}"))
        heading = section.get("heading", section_id)
        content = section.get("content", "")
        cluster_ids_raw = section.get("cluster_ids", [])
        cluster_ids = (
            [str(cluster_id) for cluster_id in cluster_ids_raw]
            if isinstance(cluster_ids_raw, list)
            else []
        )
        if not isinstance(content, str) or not content.strip():
            continue

        _render_generation_section_actions(
            payload=generation_record,
            section_id=section_id,
            heading=str(heading),
            cluster_ids=cluster_ids,
            section_output=section_outputs_by_id.get(section_id),
            key_suffix=f"e2e_{key_suffix}",
        )

        st.markdown(content)
    st.markdown("</div>", unsafe_allow_html=True)


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
    else:
        render_json_expander(payload)
