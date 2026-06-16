from __future__ import annotations

from document_pipeline_core.common.providers import GROQ_CUSTOM_MODEL_LABEL
from ui.components.provider_form import provider_model_widget_values


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
