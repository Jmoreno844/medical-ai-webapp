from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from ui.components.result_picker import render_result_picker
from ui.components.viewers import render_step_result
from ui.discovery import list_context_cases, list_templates
from ui.runner import (
    StepConfig,
    run_context_ad_hoc_pipeline_step,
    run_context_classify_clusters_step,
    run_context_cluster_spans_step,
    run_context_filter_spans_step,
    run_context_section_adapter_step,
    run_context_triage_step,
)

CONTEXT_PIPELINE_STEPS = (
    "context_triage",
    "context_filter_spans",
    "context_cluster_spans",
    "context_classify_clusters",
    "context_section_adapter",
)

CONTEXT_STEP_META = {
    "context_triage": {
        "icon": "📝",
        "color": "#795548",
        "nav_label": "Triage",
        "label": "Nota del médico → items + directivas",
    },
    "context_filter_spans": {
        "icon": "🔍",
        "color": "#607D8B",
        "nav_label": "Filter spans",
        "label": "Filtrar spans irrelevantes",
    },
    "context_cluster_spans": {
        "icon": "🗂",
        "color": "#FF9800",
        "nav_label": "Cluster spans",
        "label": "Agrupar spans en clusters",
    },
    "context_classify_clusters": {
        "icon": "🏷",
        "color": "#8BC34A",
        "nav_label": "Classify",
        "label": "Clusters → secciones del template",
    },
    "context_section_adapter": {
        "icon": "✍",
        "color": "#4CAF50",
        "nav_label": "Adapter",
        "label": "section_context por sección",
    },
}


def render_context_step_header(step: str, subtitle: str = "") -> None:
    meta = CONTEXT_STEP_META[step]
    sub_html = f"<p>{subtitle}</p>" if subtitle else ""
    st.markdown(
        f'<div class="step-page-header" style="background:{meta["color"]}18;'
        f'border-left:4px solid {meta["color"]}">'
        f'<span class="h-icon">{meta["icon"]}</span>'
        f'<div><h2 style="color:{meta["color"]}">{meta["label"]}</h2>{sub_html}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )


def render_context_stepper_nav(active_step: str) -> str:
    weights: list[float] = []
    for index in range(len(CONTEXT_PIPELINE_STEPS)):
        if index > 0:
            weights.append(0.12)
        weights.append(1.0)
    cols = st.columns(weights)

    selected = active_step
    col_index = 0
    for index, step in enumerate(CONTEXT_PIPELINE_STEPS):
        if index > 0:
            with cols[col_index]:
                st.markdown(
                    '<div style="text-align:center;color:#bbb;font-size:1.2rem;'
                    'padding-top:0.45rem;">›</div>',
                    unsafe_allow_html=True,
                )
            col_index += 1

        meta = CONTEXT_STEP_META[step]
        with cols[col_index]:
            nav_label = meta.get("nav_label", meta["label"])
            label = f"{meta['icon']} {nav_label}"
            if st.button(
                label,
                key=f"context_nav_{step}",
                type="primary" if step == active_step else "secondary",
                use_container_width=True,
            ):
                selected = step
        col_index += 1

    st.markdown('<div style="margin-bottom:0.8rem;"></div>', unsafe_allow_html=True)
    return selected


def _render_context_case_selector(key: str) -> str:
    context_cases = list_context_cases()
    if not context_cases:
        st.warning("No hay cases de contexto en cases/context/")
        return ""
    return st.selectbox("Case de contexto", context_cases, key=key)


def _step_config_from_form(step: str, key_prefix: str) -> StepConfig:
    from ui.components.provider_form import render_provider_form

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


def _persist_step_result(step: str, result_record: dict[str, object]) -> None:
    st.session_state[f"last_result_{step}"] = result_record


def _persist_step_output_path(step: str, output_path: str) -> None:
    st.session_state[f"last_output_path_{step}"] = output_path


def _render_persisted_step_result(step: str) -> None:
    result = st.session_state.get(f"last_result_{step}")
    if not isinstance(result, dict):
        return
    output_path = st.session_state.get(f"last_output_path_{step}")
    if isinstance(output_path, str) and output_path:
        st.success(f"✓ Guardado en `{output_path}`")
    render_step_result(step, result)


def _render_inspect_section(step: str) -> None:
    from ui.discovery import load_result_json

    result_meta = render_result_picker(step=step, key=f"inspect_{step}")
    if result_meta is None:
        return
    payload = load_result_json(result_meta.path)
    st.caption(f"📁 `{result_meta.path}`")
    render_step_result(step, payload)


def render_context_triage_page() -> None:
    render_context_step_header(
        "context_triage",
        "Separa directivas de contenido clínico (solo IDs)",
    )
    tab_run, tab_inspect = st.tabs(["▶ Ejecutar", "🔎 Inspeccionar"])
    with tab_inspect:
        _render_inspect_section("context_triage")
    with tab_run:
        context_case_id = _render_context_case_selector("ctx_triage_case")
        config = _step_config_from_form("context_triage", "ctx_triage_run")
        if st.button("▶ Ejecutar triage", type="primary", key="run_context_triage"):
            if not context_case_id:
                st.error("Case de contexto requerido.")
            else:
                with st.spinner("Ejecutando triage..."):
                    try:
                        output = run_context_triage_step(
                            context_case_id=context_case_id,
                            config=config,
                        )
                        _persist_step_result("context_triage", output.result_record)
                        _persist_step_output_path(
                            "context_triage",
                            str(output.output_path),
                        )
                    except Exception as exc:
                        st.error(str(exc))
        _render_persisted_step_result("context_triage")


def render_context_filter_spans_page() -> None:
    render_context_step_header("context_filter_spans", "Descarta spans irrelevantes")
    tab_run, tab_inspect = st.tabs(["▶ Ejecutar", "🔎 Inspeccionar"])
    with tab_inspect:
        _render_inspect_section("context_filter_spans")
    with tab_run:
        context_case_id = _render_context_case_selector("ctx_filter_case")
        triage_meta = render_result_picker(
            step="context_triage",
            key="ctx_filter_triage",
            allow_none=False,
        )
        config = _step_config_from_form("context_filter_spans", "ctx_filter_run")
        if st.button("▶ Filtrar spans", type="primary", key="run_context_filter"):
            if not context_case_id or triage_meta is None:
                st.error("Case y resultado de triage requeridos.")
            else:
                with st.spinner("Filtrando spans..."):
                    try:
                        output = run_context_filter_spans_step(
                            context_case_id=context_case_id,
                            config=config,
                            triage_result_path=triage_meta.path,
                        )
                        _persist_step_result(
                            "context_filter_spans",
                            output.result_record,
                        )
                        _persist_step_output_path(
                            "context_filter_spans",
                            str(output.output_path),
                        )
                    except Exception as exc:
                        st.error(str(exc))
        _render_persisted_step_result("context_filter_spans")


def render_context_cluster_spans_page() -> None:
    render_context_step_header("context_cluster_spans", "Agrupa spans relacionados")
    tab_run, tab_inspect = st.tabs(["▶ Ejecutar", "🔎 Inspeccionar"])
    with tab_inspect:
        _render_inspect_section("context_cluster_spans")
    with tab_run:
        context_case_id = _render_context_case_selector("ctx_cluster_case")
        filter_meta = render_result_picker(
            step="context_filter_spans",
            key="ctx_cluster_filter",
            allow_none=False,
        )
        config = _step_config_from_form("context_cluster_spans", "ctx_cluster_run")
        if st.button("▶ Clusterizar spans", type="primary", key="run_context_cluster"):
            if not context_case_id or filter_meta is None:
                st.error("Case y resultado de filter_spans requeridos.")
            else:
                with st.spinner("Clusterizando spans..."):
                    try:
                        output = run_context_cluster_spans_step(
                            context_case_id=context_case_id,
                            config=config,
                            filter_spans_result_path=filter_meta.path,
                        )
                        _persist_step_result(
                            "context_cluster_spans",
                            output.result_record,
                        )
                        _persist_step_output_path(
                            "context_cluster_spans",
                            str(output.output_path),
                        )
                    except Exception as exc:
                        st.error(str(exc))
        _render_persisted_step_result("context_cluster_spans")


def render_context_classify_clusters_page() -> None:
    render_context_step_header(
        "context_classify_clusters",
        "Asigna clusters a secciones del template",
    )
    tab_run, tab_inspect = st.tabs(["▶ Ejecutar", "🔎 Inspeccionar"])
    with tab_inspect:
        _render_inspect_section("context_classify_clusters")
    with tab_run:
        context_case_id = _render_context_case_selector("ctx_classify_case")
        cluster_meta = render_result_picker(
            step="context_cluster_spans",
            key="ctx_classify_cluster",
            allow_none=False,
        )
        config = _step_config_from_form(
            "context_classify_clusters",
            "ctx_classify_run",
        )
        if st.button("▶ Clasificar clusters", type="primary", key="run_context_classify"):
            if not context_case_id or cluster_meta is None:
                st.error("Case y resultado de cluster_spans requeridos.")
            else:
                with st.spinner("Clasificando clusters..."):
                    try:
                        output = run_context_classify_clusters_step(
                            context_case_id=context_case_id,
                            config=config,
                            cluster_spans_result_path=cluster_meta.path,
                        )
                        _persist_step_result(
                            "context_classify_clusters",
                            output.result_record,
                        )
                        _persist_step_output_path(
                            "context_classify_clusters",
                            str(output.output_path),
                        )
                    except Exception as exc:
                        st.error(str(exc))
        _render_persisted_step_result("context_classify_clusters")


def render_context_section_adapter_page() -> None:
    render_context_step_header(
        "context_section_adapter",
        "Genera section_context (único paso con texto clínico)",
    )
    tab_run, tab_inspect = st.tabs(["▶ Ejecutar", "🔎 Inspeccionar"])
    with tab_inspect:
        _render_inspect_section("context_section_adapter")
    with tab_run:
        context_case_id = _render_context_case_selector("ctx_adapter_case")
        classify_meta = render_result_picker(
            step="context_classify_clusters",
            key="ctx_adapter_classify",
            allow_none=False,
        )
        config = _step_config_from_form(
            "context_section_adapter",
            "ctx_adapter_run",
        )
        if st.button("▶ Ejecutar adapter", type="primary", key="run_context_adapter"):
            if not context_case_id or classify_meta is None:
                st.error("Case y resultado de classify_clusters requeridos.")
            else:
                with st.spinner("Generando section_context..."):
                    try:
                        output = run_context_section_adapter_step(
                            context_case_id=context_case_id,
                            config=config,
                            classify_clusters_result_path=classify_meta.path,
                        )
                        _persist_step_result(
                            "context_section_adapter",
                            output.result_record,
                        )
                        _persist_step_output_path(
                            "context_section_adapter",
                            str(output.output_path),
                        )
                    except Exception as exc:
                        st.error(str(exc))
        _render_persisted_step_result("context_section_adapter")


def render_context_ad_hoc_e2e_page() -> None:
    st.markdown(
        '<div class="step-page-header" style="background:#673AB718;'
        'border-left:4px solid #673AB7">'
        '<span class="h-icon">⚡</span>'
        "<div><h2 style=\"color:#673AB7\">Mini E2E contexto</h2>"
        "<p>triage → filter → cluster → classify → adapter "
        "(hasta <code>section_context</code>)</p></div></div>",
        unsafe_allow_html=True,
    )

    input_mode = st.radio(
        "Entrada",
        ["Solo PDF", "Nota del médico + PDF", "Solo nota del médico"],
        horizontal=True,
        key="ctx_adhoc_input_mode",
    )
    include_note = input_mode != "Solo PDF"
    include_pdf = input_mode != "Solo nota del médico"

    col_session, col_encounter, col_doc_date = st.columns(3)
    with col_session:
        session_id = st.text_input("Session ID", value="adhoc", key="ctx_adhoc_session")
    with col_encounter:
        encounter_date = st.text_input(
            "Fecha consulta (YYYY-MM-DD)",
            value="",
            placeholder="2026-06-14",
            key="ctx_adhoc_encounter_date",
        )
    with col_doc_date:
        document_date = st.text_input(
            "Fecha documento (opcional)",
            value="",
            placeholder="2025-10-15",
            key="ctx_adhoc_document_date",
        )

    templates = list_templates()
    template_id = st.selectbox("Template", templates, key="ctx_adhoc_template")

    doctor_note = ""
    if include_note:
        doctor_note = st.text_area(
            "Nota del médico",
            height=140,
            placeholder=(
                "No tomes casi nada de la epicrisis, solo neumonía. "
                "Paciente alérgico a penicilina."
            ),
            key="ctx_adhoc_doctor_note",
        )

    uploaded_pdf = None
    document_id = "uploaded_document"
    if include_pdf:
        uploaded_pdf = st.file_uploader(
            "Documento PDF",
            type=["pdf"],
            key="ctx_adhoc_pdf",
        )
        document_id = st.text_input(
            "document_id (para spans)",
            value="uploaded_document",
            key="ctx_adhoc_document_id",
        ).strip() or "uploaded_document"

    config = _step_config_from_form("context_pipeline", "ctx_adhoc_run")

    if st.button(
        "▶ Ejecutar mini E2E hasta adapter",
        type="primary",
        key="run_context_adhoc_e2e",
    ):
        note_text = doctor_note.strip() if include_note else None
        if include_note and not note_text:
            st.error("Escribe la nota del médico o elige otro modo de entrada.")
            return
        if include_pdf and uploaded_pdf is None:
            st.error("Sube un PDF o elige otro modo de entrada.")
            return

        pdf_path: Path | None = None
        temp_file = None
        try:
            if include_pdf and uploaded_pdf is not None:
                temp_file = tempfile.NamedTemporaryFile(
                    suffix=".pdf",
                    delete=False,
                )
                temp_file.write(uploaded_pdf.getvalue())
                temp_file.close()
                pdf_path = Path(temp_file.name)

            step_labels = [
                "triage",
                "filter_spans",
                "cluster_spans",
                "classify_clusters",
                "section_adapter",
            ]
            with st.status(
                "Ejecutando pipeline de contexto…",
                expanded=True,
            ) as status:
                for label in step_labels:
                    st.write(f"· {label}")
                try:
                    output = run_context_ad_hoc_pipeline_step(
                        session_id=session_id.strip() or "adhoc",
                        template_id=template_id,
                        config=config,
                        doctor_note=note_text,
                        document_pdf_path=pdf_path,
                        document_id=document_id,
                        encounter_date=encounter_date.strip() or None,
                        document_date=document_date.strip() or None,
                    )
                    is_partial = (
                        output.result_record.get("pipeline_status") == "partial"
                    )
                    if is_partial:
                        status.update(
                            label="⚠ Pipeline parcial (ver pasos ejecutados)",
                            state="complete",
                        )
                    else:
                        status.update(
                            label="✓ section_context generado",
                            state="complete",
                        )
                except Exception as exc:
                    status.update(label="✗ Error en pipeline", state="error")
                    st.error(str(exc))
                    return

            _persist_step_result("context_ad_hoc_pipeline", output.result_record)
            _persist_step_output_path(
                "context_ad_hoc_pipeline",
                str(output.output_path),
            )
            if output.result_record.get("pipeline_status") == "partial":
                st.warning(
                    "El pipeline se detuvo antes de completar todos los pasos. "
                    "Revisa las pestañas de los pasos que sí se ejecutaron abajo."
                )
        finally:
            if temp_file is not None:
                Path(temp_file.name).unlink(missing_ok=True)

    _render_ad_hoc_persisted_result()


def _render_ad_hoc_persisted_result() -> None:
    result = st.session_state.get("last_result_context_ad_hoc_pipeline")
    if not isinstance(result, dict):
        return
    output_path = st.session_state.get("last_output_path_context_ad_hoc_pipeline")
    if isinstance(output_path, str) and output_path:
        if result.get("pipeline_status") == "partial":
            st.warning(f"Resultado parcial guardado en `{output_path}`")
        else:
            st.success(f"✓ Guardado en `{output_path}`")
    st.subheader("Resultados por paso")
    render_step_result("context_ad_hoc_pipeline", result)


def render_context_branch_page(step_id: str) -> None:
    if step_id == "context_triage":
        render_context_triage_page()
    elif step_id == "context_filter_spans":
        render_context_filter_spans_page()
    elif step_id == "context_cluster_spans":
        render_context_cluster_spans_page()
    elif step_id == "context_classify_clusters":
        render_context_classify_clusters_page()
    else:
        render_context_section_adapter_page()
