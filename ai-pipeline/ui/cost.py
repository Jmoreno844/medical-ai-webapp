from __future__ import annotations

import streamlit as st

from common.cost_projection import CostProjectionSettings
from common.model_pricing import ANTHROPIC_PRICING_SOURCE_URL, PRICING_SOURCE_URL
from common.usage_cost import (
    UsageCostLine,
    format_usd,
    iter_e2e_usage_cost_lines,
    summarize_usage_cost_lines,
)
from ui.latency import E2E_BUCKET_ORDER, STEP_LABELS


def _cost_projection_settings_widget() -> CostProjectionSettings:
    cache_mode = st.radio(
        "Input pricing",
        options=["Sin caché", "Con caché (proyección)"],
        horizontal=True,
        key="e2e_cost_cache_mode",
        help=(
            "Sin caché: todo el input se factura a tarifa completa. "
            "Con caché: se asume que prompts estáticos (system) se reutilizan entre consultas."
        ),
    )
    include_template = True
    if cache_mode == "Con caché (proyección)":
        include_template = st.checkbox(
            "Incluir templates en caché",
            value=True,
            key="e2e_cost_cache_include_template",
            help=(
                "Si está activo, también se cuenta como caché el bloque de plantilla "
                "(classification v003 en system, generation guidelines + sección, etc.)."
            ),
        )
    return CostProjectionSettings(
        use_cache_pricing=cache_mode == "Con caché (proyección)",
        include_template_in_cache=include_template,
    )


def _cost_multiplier_widget() -> float:
    preset = st.radio(
        "Escala de proyección",
        options=["x1", "x400", "Personalizado"],
        horizontal=True,
        key="e2e_cost_scale_preset",
    )
    if preset == "x1":
        return 1.0
    if preset == "x400":
        return 400.0
    return float(
        st.number_input(
            "Multiplicador",
            min_value=1.0,
            value=1.0,
            step=1.0,
            key="e2e_cost_custom_multiplier",
        )
    )


def _detail_cost_rows(
    lines: list[UsageCostLine],
    *,
    multiplier: float,
    settings: CostProjectionSettings,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in lines:
        cached_label = f"{line.effective_cached_input_tokens:,}"
        if settings.use_cache_pricing and line.projected_cacheable_tokens > 0:
            cached_label = (
                f"{line.effective_cached_input_tokens:,} "
                f"(proj. {line.projected_cacheable_tokens:,})"
            )
        rows.append(
            {
                "Sección": line.label,
                "Modelo": f"{line.provider}/{line.model}",
                "Input": f"{line.usage.input_tokens:,}",
                "Cached": cached_label,
                "Output": f"{line.usage.output_tokens:,}",
                "Costo USD": format_usd(line.total_cost_usd, multiplier=multiplier),
            }
        )
    return rows


def _step_cost_rows(
    summary: dict[str, object],
    *,
    multiplier: float,
) -> list[dict[str, object]]:
    cost_by_step = summary.get("cost_by_step_usd")
    if not isinstance(cost_by_step, dict):
        return []

    rows: list[dict[str, object]] = []
    ordered_steps = [
        *E2E_BUCKET_ORDER,
        *(
            step
            for step in cost_by_step
            if step not in E2E_BUCKET_ORDER
        ),
    ]
    for step in ordered_steps:
        cost = cost_by_step.get(step)
        if not isinstance(step, str) or not isinstance(cost, (int, float)):
            continue
        rows.append(
            {
                "Paso": STEP_LABELS.get(step, step),
                "Costo USD": format_usd(float(cost), multiplier=multiplier),
            }
        )

    total_cost = summary.get("total_cost_usd")
    if isinstance(total_cost, (int, float)):
        rows.append(
            {
                "Paso": "Total",
                "Costo USD": format_usd(float(total_cost), multiplier=multiplier),
            }
        )
    return rows


def render_e2e_cost_summary(outputs: list[dict[str, object]]) -> None:
    projection_settings = _cost_projection_settings_widget()
    lines = iter_e2e_usage_cost_lines(outputs, settings=projection_settings)
    if not lines:
        st.info(
            "Sin datos de tokens en este run. "
            "Re-ejecuta el pipeline para capturar `llm_usage` en cada paso."
        )
        return

    summary = summarize_usage_cost_lines(lines)
    multiplier = _cost_multiplier_widget()

    st.markdown("**Costo estimado**")
    pricing_note = (
        "Basado en tokens reportados por el provider. "
        if not projection_settings.use_cache_pricing
        else (
            "Proyección con caché: prompts estáticos "
            + (
                "+ plantilla "
                if projection_settings.include_template_in_cache
                else "sin plantilla "
            )
            + "a tarifa cached. "
        )
    )
    st.caption(
        f"{pricing_note}"
        f"Tarifas OpenAI: [{PRICING_SOURCE_URL}]({PRICING_SOURCE_URL}) · "
        f"Anthropic: [{ANTHROPIC_PRICING_SOURCE_URL}]({ANTHROPIC_PRICING_SOURCE_URL})"
    )

    total_cost = summary.get("total_cost_usd")
    col_total, col_in, col_out = st.columns(3)
    col_total.metric(
        "Costo total (USD)",
        format_usd(
            float(total_cost) if isinstance(total_cost, (int, float)) else None,
            multiplier=multiplier,
        ),
        help=f"Proyección ×{multiplier:g}",
    )
    col_in.metric(
        "Input tokens",
        f"{summary.get('total_input_tokens', 0):,}",
    )
    col_out.metric(
        "Output tokens",
        f"{summary.get('total_output_tokens', 0):,}",
    )
    if projection_settings.use_cache_pricing:
        st.caption(
            f"Cached input facturado: {summary.get('total_cached_input_tokens', 0):,} · "
            f"reportado por API: {summary.get('total_reported_cached_input_tokens', 0):,}"
        )
    elif summary.get("total_reported_cached_input_tokens", 0):
        st.caption(
            f"Cached reportado por API (no aplicado en modo sin caché): "
            f"{summary.get('total_reported_cached_input_tokens', 0):,}"
        )

    if summary.get("has_unpriced_lines"):
        st.info(
            "Algunas llamadas no tienen tarifa configurada para ese modelo "
            "(OpenAI: gpt-5.4 / mini / nano; Anthropic: claude-haiku-4-5). "
            "Se muestran tokens igualmente."
        )

    step_rows = _step_cost_rows(summary, multiplier=multiplier)
    if step_rows:
        st.markdown("**Costo por paso**")
        st.dataframe(step_rows, use_container_width=True, hide_index=True)

    detail_rows = _detail_cost_rows(
        lines,
        multiplier=multiplier,
        settings=projection_settings,
    )
    with st.expander("Detalle por llamada / sección"):
        st.dataframe(detail_rows, use_container_width=True, hide_index=True)


__all__ = ["render_e2e_cost_summary"]
