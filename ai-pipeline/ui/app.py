from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import streamlit as st

AI_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(AI_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_PIPELINE_ROOT))

from classification.lib import DEFAULT_CASES_INDEX, load_session_clusters  # noqa: E402
from common.case_paths import TRANSCRIPT_CASES_INDEX  # noqa: E402
from common.transcripts import TranscriptCase, build_turn_catalog  # noqa: E402
from ui.bridge import (  # noqa: E402
    clusters_from_clustering_result,
    clusters_from_classification_record,
    missing_assignment_cluster_ids,
)
from ui.components.provider_form import (  # noqa: E402
    apply_provider_model_to_widgets,
    render_provider_form,
    render_shared_provider_controls,
)
from ui.components.result_picker import render_result_picker  # noqa: E402
from ui.components.viewers import (  # noqa: E402
    render_context_pipeline_result,
    render_e2e_document,
    render_e2e_latency_summary,
    render_step_result,
)
from ui.cost import render_e2e_cost_summary  # noqa: E402
from ui.e2e_runs import (  # noqa: E402
    list_e2e_runs,
    load_e2e_run,
    save_e2e_run,
)
from ui.e2e_pipeline import E2E_FULL_TEMPLATE_ID  # noqa: E402
from ui.e2e_viewer import (  # noqa: E402
    E2E_TRANSCRIPT_STEPS,
    build_e2e_step_states,
    context_step_from_outputs,
    extract_generation_failed_display,
    generation_succeeded,
    is_renderable_context_payload,
    resolve_e2e_pipeline_steps,
)
from ui.latency import format_latency_ms, primary_latency_ms  # noqa: E402
from ui.discovery import (  # noqa: E402
    list_classification_sessions,
    list_context_case_document_files,
    list_templates,
    list_transcript_cases,
    load_result_json,
    load_transcript_case,
    parse_transcript_case_from_json,
)
from ui.context_pages import (  # noqa: E402
    render_context_ad_hoc_e2e_page,
    render_context_classify_clusters_page,
    render_context_cluster_spans_page,
    render_context_filter_spans_page,
    render_context_section_adapter_page,
    render_context_triage_page,
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


def _generation_config_from_form(key_prefix: str) -> StepConfig:
    provider, model, prompt_version, openai_reasoning_effort = render_provider_form(
        step="generation",
        key_prefix=key_prefix,
    )
    linked_evidence_two_step = st.checkbox(
        "Linked evidence (two-step)",
        value=False,
        key=f"{key_prefix}_linked_evidence_two_step",
        help=(
            "Requiere prompt v001. ON: todas las secciones usan planner→renderer "
            "con evidence auditable (turnos tN y spans). OFF: directo (1 call), sin linking."
        ),
    )
    return StepConfig(
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        openai_reasoning_effort=openai_reasoning_effort,
        linked_evidence_two_step=linked_evidence_two_step,
    )


def _e2e_step_configs_initialized() -> bool:
    return f"e2e_{PIPELINE_STEPS[0]}_provider" in st.session_state


def _apply_e2e_shared_to_all_steps(
    *,
    provider: str,
    model: str,
    openai_reasoning_effort: str | None,
) -> None:
    for step in PIPELINE_STEPS:
        apply_provider_model_to_widgets(
            key_prefix=f"e2e_{step}",
            provider=provider,
            model=model,
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


def _session_outputs_from_persisted(
    persisted: list[dict[str, object]],
    *,
    status: str = "complete",
    failed_step: str | None = None,
    error_message: str | None = None,
    manifest_path: str | None = None,
    include_context: bool = False,
    template_id: str | None = None,
) -> None:
    st.session_state["last_e2e_outputs"] = persisted
    st.session_state["last_e2e_run_meta"] = {
        "status": status,
        "failed_step": failed_step,
        "error_message": error_message,
        "manifest_path": manifest_path,
        "include_context": include_context,
        "template_id": template_id or E2E_FULL_TEMPLATE_ID,
    }


def _persist_e2e_pipeline_result(result: object) -> Path | None:
    from ui.e2e_pipeline import E2EPipelineResult

    if not isinstance(result, E2EPipelineResult):
        return None

    clustering_output_path = ""
    for output in result.outputs:
        if output.step == "clustering":
            clustering_output_path = str(output.output_path)

    persisted: list[dict[str, object]] = []
    for output in result.outputs:
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
    _session_outputs_from_persisted(
        persisted,
        status=result.status,
        failed_step=result.failed_step,
        error_message=result.error_message,
        include_context=any(
            output.step in {"context_ad_hoc_pipeline", "context_pipeline"}
            for output in result.outputs
        ),
        template_id=E2E_FULL_TEMPLATE_ID,
    )
    return result.manifest_path


@st.fragment
def _render_e2e_history_tab() -> None:
    runs = list_e2e_runs()
    if not runs:
        st.info("No hay runs end-to-end guardados todavía.")
        return

    run_labels = [run.label for run in runs]
    selected_label = st.selectbox(
        "Run guardado",
        run_labels,
        key="e2e_history_run",
    )
    selected_run = runs[run_labels.index(selected_label)]
    st.caption(f"📁 `{selected_run.path}`")

    if st.button("Cargar run", type="primary", key="e2e_load_history"):
        try:
            loaded = load_e2e_run(selected_run.path)
            _session_outputs_from_persisted(
                loaded.outputs,
                status=loaded.status,
                failed_step=loaded.failed_step,
                error_message=loaded.error_message,
                manifest_path=str(loaded.manifest_path),
                include_context=selected_run.include_context,
                template_id=selected_run.template_id,
            )
            st.success("Run cargado.")
        except (OSError, ValueError, FileNotFoundError) as exc:
            st.error(str(exc))


@st.fragment
def _render_persisted_e2e_results() -> None:
    raw_outputs = st.session_state.get("last_e2e_outputs")
    if not isinstance(raw_outputs, list) or not raw_outputs:
        return

    run_meta = st.session_state.get("last_e2e_run_meta")
    status = "complete"
    failed_step: str | None = None
    error_message: str | None = None
    include_context = False
    if isinstance(run_meta, dict):
        status_raw = run_meta.get("status")
        if status_raw == "failed":
            status = "failed"
        failed_step_raw = run_meta.get("failed_step")
        if isinstance(failed_step_raw, str) and failed_step_raw.strip():
            failed_step = failed_step_raw
        error_message_raw = run_meta.get("error_message")
        if isinstance(error_message_raw, str) and error_message_raw.strip():
            error_message = error_message_raw
        include_context = bool(run_meta.get("include_context"))

    outputs_by_step: dict[str, dict[str, object]] = {}
    for entry in raw_outputs:
        if not isinstance(entry, dict):
            continue
        step = entry.get("step")
        if isinstance(step, str):
            outputs_by_step[step] = entry

    pipeline_steps = resolve_e2e_pipeline_steps(
        outputs_by_step,
        include_context=include_context,
    )
    step_states = build_e2e_step_states(
        pipeline_steps=pipeline_steps,
        outputs_by_step=outputs_by_step,
        status=status,
        failed_step=failed_step,
    )

    if status == "failed":
        st.error(
            f"Pipeline falló en `{failed_step or 'paso desconocido'}`"
            + (f": {error_message}" if error_message else "")
        )

    generation_entry = outputs_by_step.get("generation")
    generation_record = (
        generation_entry.get("result_record")
        if isinstance(generation_entry, dict)
        else None
    )

    tabs = st.tabs(
        [
            "📋 Documento",
            "💰 Costo",
            "🔍 Filtering",
            "🗂 Clustering",
            "🏷 Classification",
            "📝 Contexto",
            "📄 Generation",
        ]
    )

    with tabs[0]:
        if generation_succeeded(step_states) and isinstance(generation_record, dict):
            render_e2e_document(generation_record)
        elif status == "failed":
            st.info("Documento final no disponible: generation no se ejecutó.")

    with tabs[1]:
        render_e2e_cost_summary(raw_outputs)

    context_step_key = context_step_from_outputs(outputs_by_step)
    with tabs[5]:
        if context_step_key:
            context_entry = outputs_by_step.get(context_step_key)
            context_state = step_states.get(context_step_key, "not_executed")
            if context_state == "skipped":
                st.info("Paso no ejecutado.")
            elif isinstance(context_entry, dict):
                output_path = context_entry.get("output_path")
                result_record = context_entry.get("result_record")
                if isinstance(output_path, str) and output_path:
                    st.caption(f"📁 `{output_path}`")
                if context_state == "failed" and isinstance(result_record, dict):
                    st.error(
                        str(result_record.get("error_message", "Error en contexto."))
                    )
                    with st.expander("Detalle del error", expanded=False):
                        error_detail = {
                            key: result_record[key]
                            for key in (
                                "error_type",
                                "error_message",
                                "failed_step",
                                "stopped_after_step",
                                "pipeline_error",
                                "missing_span_ids",
                                "raw_response",
                            )
                            if key in result_record
                        }
                        if error_detail:
                            st.json(error_detail)
                        else:
                            st.json(result_record)
                    if is_renderable_context_payload(result_record):
                        render_context_pipeline_result(result_record)
                elif isinstance(result_record, dict):
                    render_context_pipeline_result(result_record)
            else:
                st.info("Sin contexto extra.")
        else:
            st.info("Sin contexto extra.")

    transcript_step_tabs = {
        "filtering": tabs[2],
        "clustering": tabs[3],
        "classification": tabs[4],
        "generation": tabs[6],
    }
    for step_name in E2E_TRANSCRIPT_STEPS:
        with transcript_step_tabs[step_name]:
            step_state = step_states.get(step_name, "not_executed")
            if step_state == "skipped":
                st.info("Paso no ejecutado.")
                continue
            entry = outputs_by_step.get(step_name)
            if not isinstance(entry, dict):
                st.info(f"Sin resultado para {step_name}.")
                continue
            output_path = entry.get("output_path")
            result_record = entry.get("result_record")
            if isinstance(output_path, str) and output_path:
                st.caption(f"📁 `{output_path}`")
            if step_state == "failed" and isinstance(result_record, dict):
                if step_name == "generation":
                    display = extract_generation_failed_display(result_record)
                    section_id = display.get("section_id", "desconocida")
                    substep = display.get("generation_substep", "desconocido")
                    st.error(
                        str(
                            result_record.get("error_message", "Error en generation.")
                        )
                    )
                    st.markdown(
                        f"**Sección:** `{section_id}` · "
                        f"**Subpaso:** `{substep}`"
                    )
                    provider = display.get("provider")
                    model = display.get("model")
                    prompt_version = display.get("prompt_version")
                    if provider or model or prompt_version:
                        st.caption(
                            " · ".join(
                                part
                                for part in (
                                    f"provider: `{provider}`" if provider else "",
                                    f"model: `{model}`" if model else "",
                                    f"prompt: `{prompt_version}`"
                                    if prompt_version
                                    else "",
                                )
                                if part
                            )
                        )
                    if substep == "renderer" and display.get("planner_items"):
                        with st.expander("Planner output", expanded=True):
                            if display.get("planned_items_block"):
                                st.text(str(display["planned_items_block"]))
                            st.json(display.get("planner_items"))
                else:
                    st.error(
                        str(result_record.get("error_message", "Error en el paso."))
                    )
                with st.expander("Detalle del error", expanded=True):
                    st.json(result_record)
                continue
            if isinstance(result_record, dict):
                render_step_result(step_name, result_record)

    render_e2e_latency_summary(raw_outputs)


def _render_inspect_section(step: str) -> None:
    result_meta = render_result_picker(step=step, key=f"inspect_{step}")
    if result_meta is None:
        return
    payload = load_result_json(result_meta.path)
    st.caption(f"📁 `{result_meta.path}`")
    render_step_result(step, payload)


def _render_filtering_page() -> None:
    _render_step_header("filtering", "Limpia turnos irrelevantes del transcript")
    tab_run, tab_inspect = st.tabs(["▶ Ejecutar", "🔎 Inspeccionar"])

    with tab_inspect:
        _render_inspect_section("filtering")

    with tab_run:
        with st.expander("⚙️ Configuración", expanded=False):
            config = _step_config_from_form("filtering", "filtering_run")

        cases = list_transcript_cases()
        case_labels = [f"{case.case_id}  ({case.turn_count} turns)" for case in cases]
        selected_label = st.selectbox("Transcript case", case_labels, key="filter_case")
        case_id = cases[case_labels.index(selected_label)].case_id

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
    tab_run, tab_inspect = st.tabs(["▶ Ejecutar", "🔎 Inspeccionar"])

    with tab_inspect:
        _render_inspect_section("clustering")

    with tab_run:
        with st.expander("⚙️ Configuración", expanded=False):
            config = _step_config_from_form("clustering", "clustering_run")

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
    tab_run, tab_inspect = st.tabs(["▶ Ejecutar", "🔎 Inspeccionar"])

    with tab_inspect:
        _render_inspect_section("classification")

    with tab_run:
        with st.expander("⚙️ Configuración", expanded=False):
            config = _step_config_from_form("classification", "classification_run")

        input_mode = st.radio(
            "Fuente de clusters",
            ["Fixtures (cases/cluster)", "Resultado de clustering"],
            horizontal=True,
            key="class_input_mode",
        )
        clusters = None
        session_id = ""
        template_id = ""
        clustering_result_path = ""

        if input_mode == "Fixtures (cases/cluster)":
            sessions = list_classification_sessions()
            session_labels = [
                f"{s.session_id} ({s.cluster_count} clusters)" for s in sessions
            ]
            templates = list_templates()
            col_session, col_template = st.columns(2)
            with col_session:
                selected = st.selectbox(
                    "Session",
                    session_labels,
                    key="class_session",
                )
            with col_template:
                template_id = st.selectbox(
                    "Template",
                    templates,
                    key="class_template_from_fixture",
                )
            session = sessions[session_labels.index(selected)]
            session_id = session.session_id
            clusters = load_session_clusters(DEFAULT_CASES_INDEX, session_id)
            st.caption(
                f"{session.cluster_count} clusters del fixture `{session_id}` · "
                f"template de clasificación: `{template_id}`"
            )
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
    tab_run, tab_inspect = st.tabs(["▶ Ejecutar", "🔎 Inspeccionar"])

    with tab_inspect:
        _render_inspect_section("generation")

    with tab_run:
        with st.expander("⚙️ Configuración", expanded=False):
            config = _generation_config_from_form("generation_run")

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
                ["Resultado de clustering", "Fixtures (cases/cluster)"],
                horizontal=True,
                key="gen_cluster_source",
                help="Los fixtures solo sirven si la classification se generó con esos mismos fixtures.",
            )
            if cluster_source == "Fixtures (cases/cluster)":
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

        context_result_path = None
        with st.expander("Contexto externo (opcional)", expanded=False):
            context_meta = render_result_picker(
                step="context_pipeline",
                key="gen_context_pipeline",
                label="Resultado context pipeline (section_context)",
                allow_none=True,
            )
            if context_meta is None:
                context_meta = render_result_picker(
                    step="context_section_adapter",
                    key="gen_context_adapter",
                    label="O resultado section_adapter",
                    allow_none=True,
                )
            context_result_path = (
                str(context_meta.path) if context_meta is not None else None
            )

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
                        claim_classification_result_file=context_result_path,
                    )
                    _persist_step_result("generation", output.result_record)
                    _persist_step_output_path("generation", str(output.output_path))
                except Exception as exc:
                    st.error(str(exc))

        _render_persisted_step_result("generation")



def _render_e2e_run_page() -> None:
    st.markdown("## ▶️ Pipeline end-to-end")
    _render_e2e_run_tab()


def _render_e2e_history_page() -> None:
    st.markdown("## 🕘 Historial")
    _render_e2e_history_tab()
    _render_persisted_e2e_results()


def _render_e2e_run_tab() -> None:
    case_source = st.radio(
        "Fuente del transcript",
        ["Case del repo", "Pegar JSON"],
        horizontal=True,
        key="e2e_case_source",
    )

    pasted_case = None
    case_id = ""
    turn_count = 0

    template_id = E2E_FULL_TEMPLATE_ID

    if case_source == "Case del repo":
        col_case, col_session, col_template = st.columns([2, 1.5, 1.5])
        with col_case:
            cases = list_transcript_cases()
            case_labels = [f"{c.case_id}  ({c.turn_count} turns)" for c in cases]
            selected_label = st.selectbox(
                "Transcript case",
                case_labels,
                key="e2e_case",
            )
            selected_case = cases[case_labels.index(selected_label)]
            case_id = selected_case.case_id
            turn_count = selected_case.turn_count
        with col_session:
            session_id = st.text_input(
                "Session ID",
                value=case_id,
                key="e2e_session_id",
            )
        with col_template:
            st.text_input(
                "Template",
                value=template_id,
                disabled=True,
                key="e2e_template_fixed",
            )
            st.caption(f"Plantilla fija: `{template_id}`")
    else:
        col_session, col_template = st.columns([1.5, 1.5])
        pasted_json = st.text_area(
            "Transcript case JSON",
            height=220,
            placeholder=(
                'Pega un case de ai-pipeline, p.ej. {"session_id":"case1","language":"es",'
                '"chunks":[{"chunk_id":"s0","turns":[{"turn_id":0,"speaker":"MEDICO",'
                '"text":"..."}]}]}'
            ),
            key="e2e_pasted_transcript_json",
        )
        validate_col, _ = st.columns([1, 3])
        with validate_col:
            validate_clicked = st.button(
                "Validar JSON",
                type="secondary",
                key="e2e_validate_pasted_json",
            )

        if validate_clicked:
            try:
                parsed = parse_transcript_case_from_json(pasted_json)
                st.session_state["e2e_pasted_case"] = {
                    "case_id": parsed.id,
                    "turn_count": len(build_turn_catalog(parsed.transcript_json)),
                    "session_id": str(parsed.transcript_json.get("session_id") or parsed.id),
                    "transcript_json": parsed.transcript_json,
                    "notes": parsed.notes,
                }
                st.session_state["e2e_session_id"] = st.session_state["e2e_pasted_case"][
                    "session_id"
                ]
                st.success(
                    f"JSON válido: `{parsed.id}` · "
                    f"{st.session_state['e2e_pasted_case']['turn_count']} turns"
                )
            except (ValueError, json.JSONDecodeError) as exc:
                st.session_state.pop("e2e_pasted_case", None)
                st.error(str(exc))

        pasted_state = st.session_state.get("e2e_pasted_case")
        if isinstance(pasted_state, dict):
            case_id = str(pasted_state.get("case_id") or "pasted_transcript")
            turn_count = int(pasted_state.get("turn_count") or 0)
            pasted_case = TranscriptCase(
                id=case_id,
                transcript_json=pasted_state["transcript_json"],
                notes=pasted_state.get("notes"),
            )
            st.caption(f"Case pegado: `{case_id}` · {turn_count} turns")
        else:
            st.info("Pega el JSON y pulsa **Validar JSON** antes de ejecutar el pipeline.")

        with col_session:
            default_session = case_id or "pasted_transcript"
            session_id = st.text_input(
                "Session ID",
                value=default_session,
                key="e2e_session_id",
            )
        with col_template:
            st.text_input(
                "Template",
                value=template_id,
                disabled=True,
                key="e2e_template_fixed_pasted",
            )
            st.caption(f"Plantilla fija: `{template_id}`")

    with st.expander("⚙️ Configuración", expanded=False):
        shared_provider, shared_model, shared_effort = render_shared_provider_controls(
            key_prefix="e2e_shared",
        )
        if st.button(
            "Aplicar a todos los pasos",
            type="secondary",
            key="e2e_apply_shared",
            help="Copia provider, modelo y thinking level a filtering, clustering, "
            "classification y generation.",
        ):
            _apply_e2e_shared_to_all_steps(
                provider=shared_provider,
                model=shared_model,
                openai_reasoning_effort=shared_effort,
            )
            st.rerun()

        if not _e2e_step_configs_initialized():
            _apply_e2e_shared_to_all_steps(
                provider=shared_provider,
                model=shared_model,
                openai_reasoning_effort=shared_effort,
            )

        col1, col2 = st.columns(2)
        with col1:
            with st.expander("🔍 Filtering", expanded=False):
                filtering_config = _step_config_from_form("filtering", "e2e_filtering")
            with st.expander("🏷 Classification", expanded=False):
                classification_config = _step_config_from_form(
                    "classification",
                    "e2e_classification",
                )
        with col2:
            with st.expander("🗂 Clustering", expanded=False):
                clustering_config = _step_config_from_form("clustering", "e2e_clustering")
            with st.expander("📄 Generation", expanded=False):
                generation_config = _generation_config_from_form("e2e_generation")

    with st.expander("📝 Contexto extra (opcional)", expanded=False):
        st.caption(
            "Nota libre del médico y/o PDF del paciente. Se procesa con el pipeline "
            "ad hoc de contexto y alimenta generation vía section_context."
        )
        include_context = st.checkbox(
            "Usar contexto extra",
            value=False,
            key="e2e_include_custom_context",
        )
        context_doctor_note = ""
        context_document_id = "uploaded_document"
        context_encounter_date: str | None = None
        context_document_date: str | None = None
        uploaded_pdf = None
        context_config = _step_config_from_form("context_pipeline", "e2e_context")
        if include_context:
            context_doctor_note = st.text_area(
                "Nota del médico",
                height=140,
                placeholder=(
                    "No tomes casi nada de la epicrisis, solo neumonía. "
                    "Paciente alérgico a penicilina."
                ),
                key="e2e_context_doctor_note",
            )
            uploaded_pdf = st.file_uploader(
                "Documento PDF",
                type=["pdf"],
                key="e2e_context_pdf",
            )
            context_document_id = (
                st.text_input(
                    "document_id",
                    value="uploaded_document",
                    key="e2e_context_document_id",
                ).strip()
                or "uploaded_document"
            )
            col_encounter, col_doc_date = st.columns(2)
            with col_encounter:
                encounter_raw = st.text_input(
                    "Fecha consulta (YYYY-MM-DD, opcional)",
                    value="",
                    placeholder="2026-06-14",
                    key="e2e_context_encounter_date",
                )
                context_encounter_date = encounter_raw.strip() or None
            with col_doc_date:
                doc_date_raw = st.text_input(
                    "Fecha documento (opcional)",
                    value="",
                    placeholder="2025-10-15",
                    key="e2e_context_document_date",
                )
                context_document_date = doc_date_raw.strip() or None

    st.markdown("")
    if st.button("▶ Ejecutar pipeline completo", type="primary", key="run_e2e"):
        if not session_id.strip():
            st.error("Session ID requerido.")
            return
        if case_source == "Pegar JSON":
            if pasted_case is None:
                try:
                    pasted_case = parse_transcript_case_from_json(
                        st.session_state.get("e2e_pasted_transcript_json", "")
                    )
                    case_id = pasted_case.id
                except (ValueError, json.JSONDecodeError) as exc:
                    st.error(str(exc))
                    return
            resolved_case_id = pasted_case.id
        else:
            resolved_case_id = case_id
            pasted_case = None

        if include_context:
            note_text = context_doctor_note.strip() if context_doctor_note else ""
            if not note_text and uploaded_pdf is None:
                st.error(
                    "Con contexto extra activo, escribe una nota del médico, "
                    "sube un PDF, o ambos."
                )
                return

        pdf_path: Path | None = None
        temp_pdf_file = None
        try:
            if include_context and uploaded_pdf is not None:
                temp_pdf_file = tempfile.NamedTemporaryFile(
                    suffix=".pdf",
                    delete=False,
                )
                temp_pdf_file.write(uploaded_pdf.getvalue())
                temp_pdf_file.close()
                pdf_path = Path(temp_pdf_file.name)

            with st.status("Ejecutando pipeline...", expanded=True) as status:
                pipeline_result = run_e2e_pipeline(
                    case_id=resolved_case_id,
                    session_id=session_id.strip(),
                    template_id=template_id,
                    filtering_config=filtering_config,
                    clustering_config=clustering_config,
                    classification_config=classification_config,
                    generation_config=generation_config,
                    base_case=pasted_case,
                    context_config=context_config if include_context else None,
                    context_doctor_note=context_doctor_note if include_context else None,
                    context_document_pdf_path=pdf_path,
                    context_document_id=context_document_id,
                    context_encounter_date=context_encounter_date,
                    context_document_date=context_document_date,
                )
                for output in pipeline_result.outputs:
                    result_record = output.result_record
                    step_status = result_record.get("step_status")
                    if step_status == "failed":
                        st.write(
                            f"✗ {output.step}: "
                            f"{result_record.get('error_message', 'error')}"
                        )
                        continue
                    latency = primary_latency_ms(output.step, result_record)
                    st.write(f"✓ {output.step}: {format_latency_ms(latency)}")

                manifest_path = save_e2e_run(
                    outputs=pipeline_result.outputs,
                    case_id=resolved_case_id,
                    session_id=session_id.strip(),
                    template_id=template_id,
                    include_context=include_context,
                    status=pipeline_result.status,
                    failed_step=pipeline_result.failed_step,
                    error_message=pipeline_result.error_message,
                )
                _persist_e2e_pipeline_result(pipeline_result)
                meta = st.session_state.get("last_e2e_run_meta")
                if isinstance(meta, dict):
                    meta["manifest_path"] = str(manifest_path)
                    meta["include_context"] = include_context

                if pipeline_result.status == "failed":
                    status.update(
                        label=f"✗ Falló en {pipeline_result.failed_step}",
                        state="error",
                    )
                    st.error(pipeline_result.error_message or "Error en pipeline.")
                else:
                    status.update(label="✓ Pipeline completado", state="complete")
                    st.caption(f"Run guardado en `{manifest_path}`")
        finally:
            if temp_pdf_file is not None:
                Path(temp_pdf_file.name).unlink(missing_ok=True)

    _render_persisted_e2e_results()


def main() -> None:
    load_env()
    _inject_css()

    st.sidebar.markdown("## 🩺 AI Pipeline")
    st.sidebar.caption("R&D harness")
    _check_env_sidebar()

    nav = st.navigation(
        {
            "End-to-end": [
                st.Page(
                    _render_e2e_run_page,
                    title="Run E2E",
                    icon="▶️",
                    default=True,
                ),
                st.Page(
                    _render_e2e_history_page,
                    title="Historial",
                    icon="🕘",
                ),
            ],
            "Transcript": [
                st.Page(
                    _render_filtering_page,
                    title="Filtering",
                    icon="🔍",
                ),
                st.Page(
                    _render_clustering_page,
                    title="Clustering",
                    icon="🗂",
                ),
                st.Page(
                    _render_classification_page,
                    title="Classification",
                    icon="🏷",
                ),
                st.Page(
                    _render_generation_page,
                    title="Generation",
                    icon="📄",
                ),
            ],
            "Contexto externo": [
                st.Page(
                    render_context_ad_hoc_e2e_page,
                    title="Mini E2E",
                    icon="⚡",
                ),
                st.Page(
                    render_context_triage_page,
                    title="Triage",
                    icon="🩺",
                ),
                st.Page(
                    render_context_filter_spans_page,
                    title="Filter spans",
                    icon="🔎",
                ),
                st.Page(
                    render_context_cluster_spans_page,
                    title="Cluster spans",
                    icon="🧩",
                ),
                st.Page(
                    render_context_classify_clusters_page,
                    title="Classify",
                    icon="🏷",
                ),
                st.Page(
                    render_context_section_adapter_page,
                    title="Section adapter",
                    icon="🔗",
                ),
            ],
        }
    )
    nav.run()


if __name__ == "__main__":
    main()
