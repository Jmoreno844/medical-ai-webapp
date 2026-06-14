from __future__ import annotations

import streamlit as st

from common.providers import (
    ALLOWED_PROVIDERS,
    DEFAULT_OPENAI_REASONING_EFFORT,
    GEMINI_MODEL_CHOICES,
    GROQ_CUSTOM_MODEL_LABEL,
    GROQ_MODEL_CHOICES,
    OPENAI_MODEL_CHOICES,
    OPENAI_REASONING_EFFORT_CHOICES,
    default_model_for_provider,
    normalize_provider_name,
    openai_model_supports_reasoning_effort,
)
from ui.discovery import default_prompt_version, list_prompt_versions


def _render_model_field(
    *,
    provider: str,
    model: str | None,
    key_prefix: str,
) -> str:
    default_model = default_model_for_provider(provider)
    resolved_model = (model or default_model).strip()

    if provider == "openai":
        openai_options = list(OPENAI_MODEL_CHOICES)
        if resolved_model in openai_options:
            selected_option = resolved_model
        else:
            selected_option = default_model
            if selected_option not in openai_options:
                selected_option = openai_options[0]
        return st.selectbox(
            "Model",
            options=openai_options,
            index=openai_options.index(selected_option),
            help="GPT-5.4 family. Tarifas en openai.com/api/pricing.",
            key=f"{key_prefix}_openai_model",
        )

    if provider == "gemini":
        gemini_options = list(GEMINI_MODEL_CHOICES)
        if resolved_model in gemini_options:
            selected_option = resolved_model
        else:
            selected_option = default_model
            if selected_option not in gemini_options:
                selected_option = gemini_options[0]
        return st.selectbox(
            "Model",
            options=gemini_options,
            index=gemini_options.index(selected_option),
            help=(
                "Vertex AI Gemini. Requiere GCP_PROJECT_ID; "
                "modelos 3.x usan región global."
            ),
            key=f"{key_prefix}_gemini_model",
        )

    if provider != "groq":
        return st.text_input(
            "Model",
            value=resolved_model,
            help="Vacío usa el default del provider.",
            key=f"{key_prefix}_model",
        ).strip()

    groq_options = list(GROQ_MODEL_CHOICES) + [GROQ_CUSTOM_MODEL_LABEL]
    if resolved_model in GROQ_MODEL_CHOICES:
        selected_option = resolved_model
    else:
        selected_option = GROQ_CUSTOM_MODEL_LABEL

    choice = st.selectbox(
        "Model",
        options=groq_options,
        index=groq_options.index(selected_option),
        help="Elige un modelo de Groq o escribe uno personalizado.",
        key=f"{key_prefix}_groq_model_choice",
    )
    if choice != GROQ_CUSTOM_MODEL_LABEL:
        return choice

    custom_default = (
        resolved_model
        if resolved_model not in GROQ_MODEL_CHOICES
        else default_model
    )
    return st.text_input(
        "Modelo personalizado",
        value=custom_default,
        help="ID del modelo en Groq, p.ej. qwen/qwen3-32b",
        key=f"{key_prefix}_groq_model_custom",
    ).strip()


def _render_openai_reasoning_effort_field(
    *,
    model: str,
    key_prefix: str,
    openai_reasoning_effort: str | None = None,
) -> str | None:
    if not openai_model_supports_reasoning_effort(model):
        return None

    effort_options = list(OPENAI_REASONING_EFFORT_CHOICES)
    preferred_effort = (
        openai_reasoning_effort or DEFAULT_OPENAI_REASONING_EFFORT
    ).strip().lower()
    effort_index = (
        effort_options.index(preferred_effort)
        if preferred_effort in effort_options
        else 0
    )
    return st.selectbox(
        "Thinking level",
        options=effort_options,
        index=effort_index,
        help="reasoning_effort para gpt-5.4 y gpt-5.4-mini. "
        "'none' desactiva reasoning extra.",
        key=f"{key_prefix}_openai_reasoning_effort",
    )


def provider_model_widget_values(
    *,
    key_prefix: str,
    provider: str,
    model: str,
    openai_reasoning_effort: str | None = None,
) -> dict[str, object]:
    normalized = normalize_provider_name(provider)
    default_model = default_model_for_provider(normalized)
    resolved_model = (model or default_model).strip()
    values: dict[str, object] = {f"{key_prefix}_provider": normalized}

    if normalized == "openai":
        openai_options = list(OPENAI_MODEL_CHOICES)
        selected = (
            resolved_model
            if resolved_model in openai_options
            else default_model
        )
        if selected not in openai_options:
            selected = openai_options[0]
        values[f"{key_prefix}_openai_model"] = selected
    elif normalized == "gemini":
        gemini_options = list(GEMINI_MODEL_CHOICES)
        selected = (
            resolved_model
            if resolved_model in gemini_options
            else default_model
        )
        if selected not in gemini_options:
            selected = gemini_options[0]
        values[f"{key_prefix}_gemini_model"] = selected
    elif normalized == "groq":
        if resolved_model in GROQ_MODEL_CHOICES:
            values[f"{key_prefix}_groq_model_choice"] = resolved_model
        else:
            values[f"{key_prefix}_groq_model_choice"] = GROQ_CUSTOM_MODEL_LABEL
            values[f"{key_prefix}_groq_model_custom"] = resolved_model
    else:
        values[f"{key_prefix}_model"] = resolved_model

    if (
        openai_reasoning_effort is not None
        and normalized == "openai"
        and openai_model_supports_reasoning_effort(resolved_model)
    ):
        values[f"{key_prefix}_openai_reasoning_effort"] = (
            openai_reasoning_effort.strip().lower()
        )

    return values


def apply_provider_model_to_widgets(
    *,
    key_prefix: str,
    provider: str,
    model: str,
    openai_reasoning_effort: str | None = None,
) -> None:
    for widget_key, value in provider_model_widget_values(
        key_prefix=key_prefix,
        provider=provider,
        model=model,
        openai_reasoning_effort=openai_reasoning_effort,
    ).items():
        st.session_state[widget_key] = value


def render_shared_provider_controls(
    *,
    key_prefix: str,
    provider: str | None = None,
    model: str | None = None,
    openai_reasoning_effort: str | None = None,
) -> tuple[str, str, str | None]:
    normalized_provider = normalize_provider_name(provider or ALLOWED_PROVIDERS[0])
    provider_index = (
        ALLOWED_PROVIDERS.index(normalized_provider)
        if normalized_provider in ALLOWED_PROVIDERS
        else 0
    )

    col_provider, col_model = st.columns([1, 2])
    with col_provider:
        selected_provider = st.selectbox(
            "Provider",
            options=list(ALLOWED_PROVIDERS),
            index=provider_index,
            help=(
                "Atajo para copiar provider/modelo a los 4 pasos. "
                "Cada paso sigue siendo editable abajo."
            ),
            key=f"{key_prefix}_provider",
        )
    with col_model:
        selected_model = _render_model_field(
            provider=selected_provider,
            model=model,
            key_prefix=key_prefix,
        )

    default_model = default_model_for_provider(selected_provider)
    model_for_effort = selected_model or default_model
    selected_openai_reasoning_effort: str | None = None
    if selected_provider == "openai":
        selected_openai_reasoning_effort = _render_openai_reasoning_effort_field(
            model=model_for_effort,
            key_prefix=key_prefix,
            openai_reasoning_effort=openai_reasoning_effort,
        )

    return (
        selected_provider,
        selected_model,
        selected_openai_reasoning_effort,
    )


def render_provider_form(
    *,
    step: str,
    key_prefix: str,
    provider: str | None = None,
    model: str | None = None,
    prompt_version: str | None = None,
    openai_reasoning_effort: str | None = None,
) -> tuple[str, str, str, str | None]:
    normalized_provider = normalize_provider_name(provider or ALLOWED_PROVIDERS[0])
    provider_index = (
        ALLOWED_PROVIDERS.index(normalized_provider)
        if normalized_provider in ALLOWED_PROVIDERS
        else 0
    )

    col_provider, col_model = st.columns([1, 2])
    with col_provider:
        selected_provider = st.selectbox(
            "Provider",
            options=list(ALLOWED_PROVIDERS),
            index=provider_index,
            key=f"{key_prefix}_provider",
        )
    with col_model:
        selected_model = _render_model_field(
            provider=selected_provider,
            model=model,
            key_prefix=key_prefix,
        )

    prompt_versions = list_prompt_versions(step)
    preferred = prompt_version or default_prompt_version(step)
    prompt_index = (
        prompt_versions.index(preferred) if preferred in prompt_versions else 0
    )

    default_model = default_model_for_provider(selected_provider)
    model_for_effort = selected_model or default_model
    supports_effort = (
        selected_provider == "openai"
        and openai_model_supports_reasoning_effort(model_for_effort)
    )

    selected_openai_reasoning_effort = None
    if supports_effort:
        col_prompt, col_effort = st.columns(2)
        with col_prompt:
            selected_prompt = st.selectbox(
                "Prompt version",
                options=prompt_versions,
                index=prompt_index,
                key=f"{key_prefix}_prompt",
            )
        with col_effort:
            selected_openai_reasoning_effort = _render_openai_reasoning_effort_field(
                model=model_for_effort,
                key_prefix=key_prefix,
                openai_reasoning_effort=openai_reasoning_effort,
            )
    else:
        selected_prompt = st.selectbox(
            "Prompt version",
            options=prompt_versions,
            index=prompt_index,
            key=f"{key_prefix}_prompt",
        )

    return (
        selected_provider,
        selected_model,
        selected_prompt,
        selected_openai_reasoning_effort,
    )
