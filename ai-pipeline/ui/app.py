from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

AI_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(AI_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_PIPELINE_ROOT))

from classification.lib import DEFAULT_CASES_INDEX, load_session_clusters  # noqa: E402
from ui.bridge import (  # noqa: E402
    clusters_from_clustering_result,
    clusters_from_classification_record,
    missing_assignment_cluster_ids,
)
from ui.components.provider_form import render_provider_form  # noqa: E402
from ui.components.result_picker import render_result_picker  # noqa: E402
from ui.components.viewers import (  # noqa: E402
    render_e2e_document,
    render_e2e_latency_summary,
    render_step_result,
)
from ui.latency import format_latency_ms, primary_latency_ms  # noqa: E402
from ui.discovery import (  # noqa: E402
    list_classification_sessions,
    list_context_cases,
    list_templates,
    list_transcript_cases,
    load_result_json,
    load_transcript_case,
)
from ui.runner import (  # noqa: E402
    PipelineRunOutput,
    StepConfig,
    assignments_from_classification_record,
    load_env,
    run_classification_step,
    run_clustering_step,
    run_e2e_pipeline,
    run_filtering_step,
    run_generation_step,
    transcript_case_from_filtering_result,
)

st.set_page_config(
    page_title="AI Pipeline",
    page_icon="🩺",
    layout="wide",
)

PIPELINE_STEPS = ("filtering", "clustering", "classification", "generation")

_STEP_META = {
    "filtering":      {"icon": "🔍", "color": "#2196F3", "label": "Filtering"},
    "clustering":     {"icon": "🗂",  "color": "#FF9800", "label": "Clustering"},
    "classification": {"icon": "🏷",  "color": "#9C27B0", "label": "Classification"},
    "generation":     {"icon": "📄", "color": "#4CAF50", "label": "Generation"},
}


def _inject_css() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] { min-width:220px; max-width:260px; }

        .pipeline-stepper {
            display:flex; align-items:center; gap:0;
            margin-bottom:1.2rem;
        }
        .pipeline-step {
            display:flex; flex-direction:column; align-items:center;
            padding:6px 14px; border-radius:6px;
            font-size:0.78rem; font-weight:600;
            white-space:nowrap; cursor:default;
        }
        .pipeline-step .p-icon { font-size:1.05rem; }
        .pipeline-step .p-name { font-size:0.68rem; margin-top:1px; opacity:0.85; }
        .pipeline-arrow { color:#bbb; font-size:1.1rem; padding:0 3px; flex-shrink:0; }

        .step-page-header {
            display:flex; align-items:center; gap:12px;
            padding:12px 16px; border-radius:8px; margin-bottom:1rem;
        }
        .step-page-header .h-icon { font-size:1.6rem; }
        .step-page-header h2 { margin:0; font-size:1.15rem; font-weight:700; }
        .step-page-header p  { margin:2px 0 0 0; font-size:0.72rem; opacity:0.7; }

        [data-testid="metric-container"] {
            background:rgba(0,0,0,0.04);
            border-radius:8px; padding:8px 12px;
        }

        .env-dot-ok   { color:#4CAF50; font-size:0.75rem; line-height:1.8; }
        .env-dot-warn { color:#FF9800; font-size:0.75rem; line-height:1.8; }

        .cluster-card {
            border-left:4px solid; border-radius:0 6px 6px 0;
            padding:4px 10px; margin-bottom:6px; font-size:0.8rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_pipeline_stepper(active_step: str | None = None) -> None:
    parts: list[str] = []
    for i, step in enumerate(PIPELINE_STEPS):
        meta = _STEP_META[step]
        is_active = active_step is None or step == active_step
        bg = meta["color"] if is_active else "#e8e8e8"
        color = "#fff" if is_active else "#aaa"
        parts.append(
            f'<div class="pipeline-step" style="background:{bg};color:{color}">'
            f'<span class="p-icon">{meta["icon"]}</span>'
            f'<span class="p-name">{meta["label"]}</span>'
            f"</div>"
        )
        if i < len(PIPELINE_STEPS) - 1:
            parts.append('<span class="pipeline-arrow">›</span>')

    st.markdown(
        f'<div class="pipeline-stepper">{"".join(parts)}</div>',
        unsafe_allow_html=True,
    )


def _render_step_header(step: str, subtitle: str = "") -> None:
    meta = _STEP_META[step]
    sub_html = f'<p>{subtitle}</p>' if subtitle else ""
    st.markdown(
        f'<div class="step-page-header" style="background:{meta["color"]}18;'
        f'border-left:4px solid {meta["color"]}">'
        f'<span class="h-icon">{meta["icon"]}</span>'
        f'<div><h2 style="color:{meta["color"]}">{meta["label"]}</h2>{sub_html}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )


def _check_env_sidebar() -> None:
    env_keys = [
        ("OPENAI_API_KEY",    "OpenAI"),
        ("GROQ_API_KEY",      "Groq"),
        ("ANTHROPIC_API_KEY", "Anthropic"),
        ("GCP_PROJECT_ID",    "GCP / Gemini"),
    ]
    st.sidebar.markdown("**APIs**")
    for env_var, label in env_keys:
        ok = bool(os.environ.get(env_var))
        dot = "●" if ok else "○"
        css = "env-dot-ok" if ok else "env-dot-warn"
        st.sidebar.markdown(
            f'<span class="{css}">{dot} {label}</span>',
            unsafe_allow_html=True,
        )


def _step_config_from_form(step: str, key_prefix: str) -> StepConfig:
    provider, model, prompt_version, openai_reasoning_effort = render_provider_form(
        step=step,
        key_prefix=key_prefix,
    )
    return StepConfig(
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        openai_reasoning_effort=openai_reasoning_effort,
    )


def _last_result_session_key(step: str) -> str:
    return f"last_result_{step}"


def _persist_step_result(step: str, result_record: dict[str, object]) -> None:
    st.session_state[_last_result_session_key(step)] = result_record


def _persist_step_output_path(step: str, output_path: str) -> None:
    st.session_state[f"last_output_path_{step}"] = output_path


@st.fragment
def _render_persisted_step_result(step: str) -> None:
    result = st.session_state.get(_last_result_session_key(step))
    if not isinstance(result, dict):
        return
    output_path = st.session_state.get(f"last_output_path_{step}")
    if isinstance(output_path, str) and output_path:
        latency = primary_latency_ms(step, result)
        latency_label = format_latency_ms(latency)
        st.success(f"✓ Guardado en `{output_path}` · {latency_label}")
    render_step_result(step, result)


def _persist_e2e_outputs(outputs: list[PipelineRunOutput]) -> None:
    clustering_output_path = ""
    for output in outputs:
        if output.step == "clustering":
            clustering_output_path = str(output.output_path)

    persisted: list[dict[str, object]] = []
    for output in outputs:
        result_record = dict(output.result_record)
        if clustering_output_path and output.step in {
            "classification",
            "generation",
        }:
            result_record.setdefault(
                "clustering_result_file",
                clustering_output_path,
            )
        persisted.append(
            {
                "step": output.step,
                "result_record": result_record,
                "output_path": str(output.output_path),
            }
        )
    st.session_state["last_e2e_outputs"] = persisted


@st.fragment
def _render_persisted_e2e_results() -> None:
    raw_outputs = st.session_state.get("last_e2e_outputs")
    if not isinstance(raw_outputs, list) or not raw_outputs:
        return

    render_e2e_latency_summary(raw_outputs)

    tabs = st.tabs(
        [
            "📋 Documento",
            "🔍 Filtering",
            "🗂 Clustering",
            "🏷 Classification",
            "📄 Generation",
        ]
    )
    generation_record = raw_outputs[-1]["result_record"]
    with tabs[0]:
        if isinstance(generation_record, dict):
            render_e2e_document(generation_record)
    for index, step_name in enumerate(PIPELINE_STEPS):
        with tabs[index + 1]:
            entry = raw_outputs[index]
            if not isinstance(entry, dict):
                continue
            output_path = entry.get("output_path")
            result_record = entry.get("result_record")
            if isinstance(output_path, str) and output_path:
                st.caption(f"📁 `{output_path}`")
            if isinstance(result_record, dict):
                render_step_result(step_name, result_record)


def _render_inspect_section(step: str) -> None:
    result_meta = render_result_picker(step=step, key=f"inspect_{step}")
    if result_meta is None:
        return
    payload = load_result_json(result_meta.path)
    st.caption(f"📁 `{result_meta.path}`")
    render_step_result(step, payload)


def _render_filtering_page() -> None:
    _render_step_header("filtering", "Limpia turnos irrelevantes del transcript")
    _render_pipeline_stepper("filtering")
    tab_run, tab_inspect = st.tabs(["▶ Ejecutar", "🔎 Inspeccionar"])

    with tab_inspect:
        _render_inspect_section("filtering")

    with tab_run:
        cases = list_transcript_cases()
        case_labels = [f"{case.case_id}  ({case.turn_count} turns)" for case in cases]
        selected_label = st.selectbox("Transcript case", case_labels, key="filter_case")
        case_id = cases[case_labels.index(selected_label)].case_id

        config = _step_config_from_form("filtering", "filtering_run")
        if st.button("▶ Ejecutar filtering", type="primary", key="run_filtering"):
            with st.spinner("Ejecutando filtering..."):
                try:
                    output = run_filtering_step(
                        case=load_transcript_case(case_id),
                        config=config,
                    )
                    _persist_step_result("filtering", output.result_record)
                    _persist_step_output_path("filtering", str(output.output_path))
                except Exception as exc:
                    st.error(str(exc))

        _render_persisted_step_result("filtering")


def _render_clustering_page() -> None:
    _render_step_header("clustering", "Agrupa turnos en clusters temáticos")
    _render_pipeline_stepper("clustering")
    tab_run, tab_inspect = st.tabs(["▶ Ejecutar", "🔎 Inspeccionar"])

    with tab_inspect:
        _render_inspect_section("clustering")

    with tab_run:
        input_mode = st.radio(
            "Fuente de input",
            ["Transcript case", "Resultado de filtering"],
            horizontal=True,
            key="cluster_input_mode",
        )
        case = None
        if input_mode == "Transcript case":
            cases = list_transcript_cases()
            case_labels = [
                f"{case.case_id}  ({case.turn_count} turns)" for case in cases
            ]
            selected_label = st.selectbox(
                "Transcript case", case_labels, key="cluster_case"
            )
            case_id = cases[case_labels.index(selected_label)].case_id
            case = load_transcript_case(case_id)
        else:
            filter_meta = render_result_picker(
                step="filtering", key="cluster_filter_result", allow_none=False
            )
            if filter_meta is not None:
                filtering_record = load_result_json(filter_meta.path)
                filter_case_id = filtering_record.get("case_id")
                if not isinstance(filter_case_id, str):
                    st.error("El resultado de filtering no tiene case_id.")
                    return
                base_case = load_transcript_case(filter_case_id)
                case = transcript_case_from_filtering_result(
                    base_case=base_case, filtering_record=filtering_record
                )
                st.caption(
                    f"Transcript filtrado de `{filter_case_id}` ({filter_meta.label})"
                )

        config = _step_config_from_form("clustering", "clustering_run")
        if st.button("▶ Ejecutar clustering", type="primary", key="run_clustering"):
            if case is None:
                st.error("Selecciona un input válido.")
                return
            with st.spinner("Ejecutando clustering..."):
                try:
                    output = run_clustering_step(case=case, config=config)
                    _persist_step_result("clustering", output.result_record)
                    _persist_step_output_path("clustering", str(output.output_path))
                except Exception as exc:
                    st.error(str(exc))

        _render_persisted_step_result("clustering")


def _render_classification_page() -> None:
    _render_step_header("classification", "Asigna clusters a secciones del template")
    _render_pipeline_stepper("classification")
    tab_run, tab_inspect = st.tabs(["▶ Ejecutar", "🔎 Inspeccionar"])

    with tab_inspect:
        _render_inspect_section("classification")

    with tab_run:
        input_mode = st.radio(
            "Fuente de clusters",
            ["Fixtures (classification/cases)", "Resultado de clustering"],
            horizontal=True,
            key="class_input_mode",
        )
        clusters = None
        session_id = ""
        template_id = ""
        clustering_result_path = ""

        if input_mode == "Fixtures (classification/cases)":
            sessions = list_classification_sessions()
            session_labels = [
                f"{s.session_id}  ({s.cluster_count} clusters, {s.template_id})"
                for s in sessions
            ]
            selected = st.selectbox("Session", session_labels, key="class_session")
            session = sessions[session_labels.index(selected)]
            session_id = session.session_id
            template_id = session.template_id
            clusters = load_session_clusters(DEFAULT_CASES_INDEX, session_id)
        else:
            cluster_meta = render_result_picker(
                step="clustering", key="class_cluster_result", allow_none=False
            )
            col_t, col_s = st.columns(2)
            with col_t:
                templates = list_templates()
                template_id = st.selectbox(
                    "Template", templates, key="class_template_from_cluster"
                )
            with col_s:
                session_id = st.text_input(
                    "Session ID",
                    value="case1",
                    help="Prefijo para cluster ids, p.ej. case1 → case1_topic_label",
                    key="class_session_from_cluster",
                )
            if cluster_meta is not None and session_id.strip():
                clustering_record = load_result_json(cluster_meta.path)
                clusters = clusters_from_clustering_result(
                    clustering_record,
                    session_id=session_id.strip(),
                    template_id=template_id,
                )
                st.caption(
                    f"{len(clusters)} clusters desde `{cluster_meta.path.name}`"
                )
                clustering_result_path = str(cluster_meta.path)
            else:
                clustering_result_path = ""

        config = _step_config_from_form("classification", "classification_run")
        if st.button(
            "▶ Ejecutar classification", type="primary", key="run_classification"
        ):
            if clusters is None or not session_id.strip():
                st.error("Selecciona un input válido.")
                return
            with st.spinner("Ejecutando classification..."):
                try:
                    output = run_classification_step(
                        session_id=session_id.strip(),
                        clusters=clusters,
                        template_id=template_id,
                        config=config,
                        clustering_result_file=clustering_result_path or None,
                    )
                    _persist_step_result("classification", output.result_record)
                    _persist_step_output_path(
                        "classification",
                        str(output.output_path),
                    )
                except Exception as exc:
                    st.error(str(exc))

        _render_persisted_step_result("classification")


def _render_generation_page() -> None:
    _render_step_header("generation", "Genera el documento médico estructurado")
    _render_pipeline_stepper("generation")
    tab_run, tab_inspect = st.tabs(["▶ Ejecutar", "🔎 Inspeccionar"])

    with tab_inspect:
        _render_inspect_section("generation")

    with tab_run:
        class_meta = render_result_picker(
            step="classification",
            key="gen_class_result",
            label="Resultado de classification",
            allow_none=False,
        )

        clusters = None
        session_id = ""
        template_id = ""
        assignments = None
        classification_path = ""
        clustering_result_path = ""

        if class_meta is not None:
            classification_record = load_result_json(class_meta.path)
            classification_path = str(class_meta.path)
            session_id_raw = classification_record.get("session_id")
            template_id_raw = classification_record.get("template_id")
            if isinstance(session_id_raw, str):
                session_id = session_id_raw
            if isinstance(template_id_raw, str):
                template_id = template_id_raw
            assignments = assignments_from_classification_record(classification_record)
            st.caption(f"Session `{session_id}` · template `{template_id}`")

            try:
                clusters, linked_clustering_path = clusters_from_classification_record(
                    classification_record
                )
                clustering_result_path = str(linked_clustering_path)
                missing_ids = missing_assignment_cluster_ids(
                    assignment_cluster_ids=[
                        assignment.cluster_id for assignment in assignments
                    ],
                    clusters=clusters,
                )
                st.success(
                    f"Clusters enlazados desde `{linked_clustering_path.name}` "
                    f"({len(clusters)} clusters). "
                    "Deben coincidir exactamente con los `cluster_id` de esta classification."
                )
                if missing_ids:
                    st.error(
                        "Esta classification referencia cluster_id que no están en su "
                        f"clustering enlazado: `{missing_ids}`"
                    )
                    clusters = None
            except ValueError as exc:
                st.warning(
                    "Este resultado de classification no trae un clustering enlazado "
                    f"usable ({exc}). Elige una fuente de clusters abajo."
                )

        with st.expander("Fuente de clusters (solo si no hay enlace automático)"):
            cluster_source = st.radio(
                "Fuente de clusters",
                ["Resultado de clustering", "Fixtures (classification/cases)"],
                horizontal=True,
                key="gen_cluster_source",
                help="Los fixtures solo sirven si la classification se generó con esos mismos fixtures.",
            )
            if cluster_source == "Fixtures (classification/cases)":
                st.caption(
                    "Los fixtures son un snapshot fijo con otros `cluster_id`. "
                    "No funcionan con classification de un clustering nuevo."
                )
                if session_id:
                    try:
                        fixture_clusters = load_session_clusters(
                            DEFAULT_CASES_INDEX,
                            session_id,
                        )
                        if assignments is not None:
                            missing_ids = missing_assignment_cluster_ids(
                                assignment_cluster_ids=[
                                    assignment.cluster_id
                                    for assignment in assignments
                                ],
                                clusters=fixture_clusters,
                            )
                            if missing_ids:
                                st.error(
                                    "Fixtures incompatibles con esta classification. "
                                    f"Faltan: `{missing_ids}`"
                                )
                            else:
                                clusters = fixture_clusters
                                clustering_result_path = ""
                                st.info(
                                    f"Usando {len(fixture_clusters)} clusters de fixtures."
                                )
                        else:
                            clusters = fixture_clusters
                    except ValueError as exc:
                        st.warning(str(exc))
            elif session_id and template_id:
                cluster_meta = render_result_picker(
                    step="clustering",
                    key="gen_cluster_result",
                    allow_none=False,
                )
                if cluster_meta is not None:
                    clustering_record = load_result_json(cluster_meta.path)
                    manual_clusters = clusters_from_clustering_result(
                        clustering_record,
                        session_id=session_id,
                        template_id=template_id,
                    )
                    if assignments is not None:
                        missing_ids = missing_assignment_cluster_ids(
                            assignment_cluster_ids=[
                                assignment.cluster_id for assignment in assignments
                            ],
                            clusters=manual_clusters,
                        )
                        if missing_ids:
                            st.error(
                                "Este clustering no coincide con la classification. "
                                f"Faltan: `{missing_ids}`"
                            )
                        else:
                            clusters = manual_clusters
                            clustering_result_path = str(cluster_meta.path)
                            st.info(
                                f"Usando {len(manual_clusters)} clusters desde "
                                f"`{cluster_meta.path.name}`."
                            )
                    else:
                        clusters = manual_clusters
                        clustering_result_path = str(cluster_meta.path)

        config = _step_config_from_form("generation", "generation_run")
        if st.button("▶ Ejecutar generation", type="primary", key="run_generation"):
            if (
                clusters is None
                or assignments is None
                or not session_id
                or not template_id
            ):
                st.error("Selecciona classification result y clusters válidos.")
                return
            with st.spinner("Ejecutando generation..."):
                try:
                    output = run_generation_step(
                        session_id=session_id,
                        clusters=clusters,
                        assignments=assignments,
                        template_id=template_id,
                        config=config,
                        classification_result_file=classification_path,
                        clustering_result_file=clustering_result_path or None,
                    )
                    _persist_step_result("generation", output.result_record)
                    _persist_step_output_path("generation", str(output.output_path))
                except Exception as exc:
                    st.error(str(exc))

        _render_persisted_step_result("generation")


def _render_e2e_page() -> None:
    st.markdown("## 🩺 Pipeline end-to-end")
    _render_pipeline_stepper(active_step=None)

    col_case, col_session, col_template = st.columns([2, 1.5, 1.5])
    with col_case:
        cases = list_transcript_cases()
        case_labels = [f"{c.case_id}  ({c.turn_count} turns)" for c in cases]
        selected_label = st.selectbox("Transcript case", case_labels, key="e2e_case")
        case_id = cases[case_labels.index(selected_label)].case_id
    with col_session:
        session_id = st.text_input("Session ID", value=case_id, key="e2e_session_id")
    with col_template:
        templates = list_templates()
        template_id = st.selectbox("Template", templates, key="e2e_template")

    st.markdown("---")
    st.markdown("**Configuración por paso**")
    col1, col2 = st.columns(2)
    with col1:
        with st.expander("🔍 Filtering", expanded=False):
            filtering_config = _step_config_from_form("filtering", "e2e_filtering")
        with st.expander("🏷 Classification", expanded=False):
            classification_config = _step_config_from_form(
                "classification", "e2e_classification"
            )
    with col2:
        with st.expander("🗂 Clustering", expanded=False):
            clustering_config = _step_config_from_form("clustering", "e2e_clustering")
        with st.expander("📄 Generation", expanded=False):
            generation_config = _step_config_from_form("generation", "e2e_generation")

    with st.expander("📝 Context pipeline (opcional)", expanded=False):
        include_context = st.checkbox(
            "Incluir contexto médico + documentos",
            value=False,
            key="e2e_include_context",
        )
        context_case_id = case_id
        context_config = _step_config_from_form("context_decompose", "e2e_context")
        if include_context:
            context_cases = list_context_cases()
            if context_cases:
                context_case_id = st.selectbox(
                    "Context case",
                    context_cases,
                    index=context_cases.index(case_id)
                    if case_id in context_cases
                    else 0,
                    key="e2e_context_case",
                )
            else:
                st.warning("No hay context cases en context_pipeline/cases/")

    st.markdown("")
    if st.button("▶ Ejecutar pipeline completo", type="primary", key="run_e2e"):
        if not session_id.strip():
            st.error("Session ID requerido.")
            return
        with st.status("Ejecutando pipeline...", expanded=True) as status:
            try:
                outputs = run_e2e_pipeline(
                    case_id=case_id,
                    session_id=session_id.strip(),
                    template_id=template_id,
                    filtering_config=filtering_config,
                    clustering_config=clustering_config,
                    classification_config=classification_config,
                    generation_config=generation_config,
                    context_case_id=context_case_id if include_context else None,
                    context_config=context_config if include_context else None,
                )
                for output in outputs:
                    latency = primary_latency_ms(
                        output.step,
                        output.result_record,
                    )
                    st.write(
                        f"✓ {output.step}: {format_latency_ms(latency)}"
                    )
                status.update(label="✓ Pipeline completado", state="complete")
                _persist_e2e_outputs(outputs)
            except Exception as exc:
                status.update(label="✗ Error en pipeline", state="error")
                st.error(str(exc))
                return

    _render_persisted_e2e_results()


def main() -> None:
    load_env()
    _inject_css()

    st.sidebar.markdown("## 🩺 AI Pipeline")
    st.sidebar.caption("R&D harness")
    st.sidebar.divider()

    mode = st.sidebar.radio(
        "Modo",
        ["End-to-end", "Paso individual"],
        key="nav_mode",
    )

    step: str | None = None
    if mode == "Paso individual":
        step = st.sidebar.selectbox(
            "Paso",
            ["Filtering", "Clustering", "Classification", "Generation"],
            key="nav_step",
        )

    st.sidebar.divider()
    _check_env_sidebar()

    if mode == "End-to-end":
        _render_e2e_page()
        return

    if step == "Filtering":
        _render_filtering_page()
    elif step == "Clustering":
        _render_clustering_page()
    elif step == "Classification":
        _render_classification_page()
    else:
        _render_generation_page()


if __name__ == "__main__":
    main()
