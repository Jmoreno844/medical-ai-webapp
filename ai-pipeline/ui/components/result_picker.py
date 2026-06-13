from __future__ import annotations

from pathlib import Path

import streamlit as st

from ui.discovery import ResultMeta, list_results, load_result_json


def render_result_picker(
    *,
    step: str,
    key: str,
    label: str = "Resultado previo",
    allow_none: bool = True,
) -> ResultMeta | None:
    results = list_results(step)
    if not results:
        st.info(f"No hay resultados guardados en {step}/results/.")
        return None

    options: list[str] = []
    if allow_none:
        options.append("(ninguno)")
    options.extend(result.label for result in results)

    selection = st.selectbox(label, options=options, key=key)
    if allow_none and selection == "(ninguno)":
        return None
    for result in results:
        if result.label == selection:
            return result
    return None


def render_inspect_button(
    *,
    result_meta: ResultMeta | None,
    key: str,
) -> dict[str, object] | None:
    if result_meta is None:
        return None
    if st.button("Inspeccionar resultado", key=key):
        return load_result_json(result_meta.path)
    return None


def result_path_label(path: Path) -> str:
    return str(path)
