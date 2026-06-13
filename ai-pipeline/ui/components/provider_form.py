from __future__ import annotations

import streamlit as st

from common.providers import (
    ALLOWED_PROVIDERS,
    DEFAULT_OPENAI_REASONING_EFFORT,
    GROQ_CUSTOM_MODEL_LABEL,
    GROQ_MODEL_CHOICES,
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

    selected_openai_reasoning_effort: str | None = None
    default_model = default_model_for_provider(selected_provider)
    model_for_effort = selected_model or default_model
    supports_effort = (
        selected_provider == "openai"
        and openai_model_supports_reasoning_effort(model_for_effort)
    )

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
            effort_options = list(OPENAI_REASONING_EFFORT_CHOICES)
            preferred_effort = (
                openai_reasoning_effort or DEFAULT_OPENAI_REASONING_EFFORT
            ).strip().lower()
            effort_index = (
                effort_options.index(preferred_effort)
                if preferred_effort in effort_options
                else 0
            )
            selected_openai_reasoning_effort = st.selectbox(
                "Thinking level",
                options=effort_options,
                index=effort_index,
                help="reasoning_effort para gpt-5.4 y gpt-5.4-mini. "
                "'none' desactiva reasoning extra.",
                key=f"{key_prefix}_openai_reasoning_effort",
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
