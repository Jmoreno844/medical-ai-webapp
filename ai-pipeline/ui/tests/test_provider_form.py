from __future__ import annotations

import pytest

from document_pipeline_core.common.providers import GROQ_CUSTOM_MODEL_LABEL
from ui.components.provider_form import (
    model_from_session_state,
    provider_model_widget_values,
    step_config_from_session_state,
)


def test_provider_model_widget_values_openai() -> None:
    values = provider_model_widget_values(
        key_prefix="e2e_filtering",
        provider="openai",
        model="gpt-5.4-mini",
        openai_reasoning_effort="low",
    )
    assert values == {
        "e2e_filtering_provider": "openai",
        "e2e_filtering_openai_model": "gpt-5.4-mini",
        "e2e_filtering_openai_reasoning_effort": "low",
    }


def test_provider_model_widget_values_gemini() -> None:
    values = provider_model_widget_values(
        key_prefix="e2e_clustering",
        provider="gemini",
        model="gemini-2.5-flash",
        openai_reasoning_effort=None,
    )
    assert values == {
        "e2e_clustering_provider": "gemini",
        "e2e_clustering_gemini_model": "gemini-2.5-flash",
    }


def test_provider_model_widget_values_groq_custom() -> None:
    values = provider_model_widget_values(
        key_prefix="e2e_generation",
        provider="groq",
        model="custom/model",
        openai_reasoning_effort=None,
    )
    assert values == {
        "e2e_generation_provider": "groq",
        "e2e_generation_groq_model_choice": GROQ_CUSTOM_MODEL_LABEL,
        "e2e_generation_groq_model_custom": "custom/model",
    }


def test_model_from_session_state_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    import streamlit as st

    monkeypatch.setattr(
        st,
        "session_state",
        {
            "classification_run_provider": "gemini",
            "classification_run_gemini_model": "gemini-2.5-flash",
        },
    )
    assert model_from_session_state("classification_run", "gemini") == "gemini-2.5-flash"


def test_step_config_from_session_state_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import streamlit as st

    monkeypatch.setattr(
        st,
        "session_state",
        {
            "classification_run_provider": "gemini",
            "classification_run_gemini_model": "gemini-2.5-flash",
            "classification_run_prompt": "v001",
        },
    )
    config = step_config_from_session_state(
        "classification",
        "classification_run",
        prompt_versions=["v001"],
        default_prompt_version_override="v001",
    )
    assert config.provider == "gemini"
    assert config.model == "gemini-2.5-flash"
    assert config.prompt_version == "v001"
