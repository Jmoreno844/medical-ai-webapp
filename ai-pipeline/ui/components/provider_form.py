from __future__ import annotations

import streamlit as st

from document_pipeline_core.common.providers import (
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


def _provider_widget_index(key_prefix: str, fallback_provider: str) -> int:
    provider_key = f"{key_prefix}_provider"
    current = st.session_state.get(provider_key)
    if isinstance(current, str):
        normalized = normalize_provider_name(current)
        if normalized in ALLOWED_PROVIDERS:
            return ALLOWED_PROVIDERS.index(normalized)
    fallback = normalize_provider_name(fallback_provider)
    if fallback in ALLOWED_PROVIDERS:
        return ALLOWED_PROVIDERS.index(fallback)
    return 0


def model_from_session_state(key_prefix: str, provider: str) -> str:
    normalized = normalize_provider_name(provider)
    default_model = default_model_for_provider(normalized)

    if normalized == "openai":
        value = st.session_state.get(f"{key_prefix}_openai_model")
    elif normalized == "gemini":
        value = st.session_state.get(f"{key_prefix}_gemini_model")
    elif normalized == "groq":
        choice = st.session_state.get(f"{key_prefix}_groq_model_choice")
        if choice == GROQ_CUSTOM_MODEL_LABEL:
            value = st.session_state.get(f"{key_prefix}_groq_model_custom")
        else:
            value = choice
    else:
        value = st.session_state.get(f"{key_prefix}_model")

    if isinstance(value, str) and value.strip():
        return value.strip()
    return default_model


def openai_reasoning_effort_from_session_state(
    key_prefix: str,
    *,
    provider: str,
    model: str,
) -> str | None:
    normalized = normalize_provider_name(provider)
    if normalized != "openai" or not openai_model_supports_reasoning_effort(model):
        return None
    effort = st.session_state.get(f"{key_prefix}_openai_reasoning_effort")
    if isinstance(effort, str) and effort.strip():
        return effort.strip().lower()
    return DEFAULT_OPENAI_REASONING_EFFORT


def step_config_from_session_state(
    step: str,
    key_prefix: str,
    *,
    prompt_versions: list[str] | None = None,
    default_prompt_version_override: str | None = None,
    prompt_version_key_suffix: str = "",
    generation_route: str = "direct",
) -> "StepConfig":
    from ui.runner import StepConfig

    provider_key = f"{key_prefix}_provider"
    provider = normalize_provider_name(
        str(st.session_state.get(provider_key, ALLOWED_PROVIDERS[0]))
    )
    model = model_from_session_state(key_prefix, provider)
    versions = prompt_versions if prompt_versions is not None else list_prompt_versions(step)
    preferred = (
        default_prompt_version_override
        or default_prompt_version(step)
    )
    prompt_key = f"{key_prefix}_prompt{prompt_version_key_suffix}"
    prompt_raw = st.session_state.get(prompt_key, preferred)
    prompt_version = str(prompt_raw) if prompt_raw is not None else preferred
    if prompt_version not in versions and versions:
        prompt_version = preferred if preferred in versions else versions[0]

    return StepConfig(
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        openai_reasoning_effort=openai_reasoning_effort_from_session_state(
            key_prefix,
            provider=provider,
            model=model,
        ),
        generation_route=generation_route,
        linked_evidence_two_step=generation_route == "two_step",
    )


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
    fallback_provider = normalize_provider_name(provider or ALLOWED_PROVIDERS[0])
    provider_key = f"{key_prefix}_provider"
    if provider_key not in st.session_state:
        st.session_state[provider_key] = fallback_provider

    col_provider, col_model = st.columns([1, 2])
    with col_provider:
        selected_provider = st.selectbox(
            "Provider",
            options=list(ALLOWED_PROVIDERS),
            index=_provider_widget_index(key_prefix, fallback_provider),
            help=(
                "Atajo para copiar provider/modelo a los 4 pasos. "
                "Cada paso sigue siendo editable abajo."
            ),
            key=provider_key,
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
    prompt_versions: list[str] | None = None,
    default_prompt_version_override: str | None = None,
    prompt_version_help: str | None = None,
    prompt_version_key_suffix: str = "",
) -> tuple[str, str, str, str | None]:
    fallback_provider = normalize_provider_name(provider or ALLOWED_PROVIDERS[0])
    provider_key = f"{key_prefix}_provider"
    if provider_key not in st.session_state:
        st.session_state[provider_key] = fallback_provider

    col_provider, col_model = st.columns([1, 2])
    with col_provider:
        selected_provider = st.selectbox(
            "Provider",
            options=list(ALLOWED_PROVIDERS),
            index=_provider_widget_index(key_prefix, fallback_provider),
            key=provider_key,
        )
    with col_model:
        selected_model = _render_model_field(
            provider=selected_provider,
            model=model,
            key_prefix=key_prefix,
        )

    versions = prompt_versions if prompt_versions is not None else list_prompt_versions(step)
    preferred = (
        prompt_version
        or default_prompt_version_override
        or default_prompt_version(step)
    )
    prompt_index = versions.index(preferred) if preferred in versions else 0
    prompt_key = f"{key_prefix}_prompt{prompt_version_key_suffix}"

    default_model = default_model_for_provider(selected_provider)
    model_for_effort = selected_model or default_model
    supports_effort = (
        selected_provider == "openai"
        and openai_model_supports_reasoning_effort(model_for_effort)
    )

    def _render_prompt_field() -> str:
        if len(versions) == 1:
            only_version = versions[0]
            st.caption(f"Prompt: **{only_version}**")
            if prompt_version_help:
                st.caption(prompt_version_help)
            return only_version
        return st.selectbox(
            "Prompt version",
            options=versions,
            index=prompt_index,
            help=prompt_version_help,
            key=prompt_key,
        )

    selected_openai_reasoning_effort = None
    if supports_effort:
        col_prompt, col_effort = st.columns(2)
        with col_prompt:
            selected_prompt = _render_prompt_field()
        with col_effort:
            selected_openai_reasoning_effort = _render_openai_reasoning_effort_field(
                model=model_for_effort,
                key_prefix=key_prefix,
                openai_reasoning_effort=openai_reasoning_effort,
            )
    else:
        selected_prompt = _render_prompt_field()

    return (
        selected_provider,
        selected_model,
        selected_prompt,
        selected_openai_reasoning_effort,
    )
