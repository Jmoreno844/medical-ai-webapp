from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal


ProviderFamily = Literal["google", "openai", "anthropic"]

_SUPPORTED_PROVIDER_FAMILIES = {"google", "openai", "anthropic"}


@dataclass(frozen=True, slots=True)
class LlmProviderSpec:
    provider_family: ProviderFamily
    model_name: str
    google_location: str | None = None


def _normalize_provider_family(value: Any) -> ProviderFamily:
    normalized = str(value or "").strip().lower()
    if normalized not in _SUPPORTED_PROVIDER_FAMILIES:
        raise ValueError(
            "Unsupported LLM provider family: "
            f"{value!r}. Expected one of: {', '.join(sorted(_SUPPORTED_PROVIDER_FAMILIES))}."
        )
    return normalized  # type: ignore[return-value]


def _default_model_name(provider_family: ProviderFamily, *, legacy_google_model: str | None) -> str:
    if provider_family == "google":
        return str(legacy_google_model or "gemini-2.5-flash")
    if provider_family == "openai":
        return "gpt-5.4-mini"
    return "claude-haiku-4-5"


def resolve_runtime_provider_specs(settings: Any) -> tuple[LlmProviderSpec, LlmProviderSpec]:
    base_provider = _normalize_provider_family(
        getattr(settings, "llm_provider_family", "openai")
    )
    legacy_google_model = getattr(settings, "vertex_model", None)
    base_google_location = (
        getattr(settings, "google_location", None) or getattr(settings, "gcp_region", None)
    )

    planner_provider = _normalize_provider_family(
        getattr(settings, "planner_provider_family", None) or base_provider
    )
    planner_model = str(
        getattr(settings, "planner_model", None)
        or _default_model_name(
            planner_provider,
            legacy_google_model=legacy_google_model,
        )
    )
    planner_google_location = (
        getattr(settings, "planner_google_location", None) or base_google_location
    )
    planner_spec = LlmProviderSpec(
        provider_family=planner_provider,
        model_name=planner_model,
        google_location=planner_google_location,
    )

    raw_patch_provider = getattr(settings, "patch_provider_family", None)
    patch_provider = _normalize_provider_family(raw_patch_provider or base_provider)
    if getattr(settings, "patch_model", None):
        patch_model = str(getattr(settings, "patch_model"))
    elif raw_patch_provider is None:
        # If the patch provider was not overridden, keep planner+patch aligned by default.
        patch_model = planner_model
    else:
        patch_model = _default_model_name(
            patch_provider,
            legacy_google_model=legacy_google_model,
        )
    patch_google_location = (
        getattr(settings, "patch_google_location", None) or base_google_location
    )
    patch_spec = LlmProviderSpec(
        provider_family=patch_provider,
        model_name=patch_model,
        google_location=patch_google_location,
    )

    return planner_spec, patch_spec


def build_langchain_chat_model(
    *,
    settings: Any,
    provider_spec: LlmProviderSpec,
    temperature: float,
    max_tokens: int,
) -> Any:
    if provider_spec.provider_family == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        project_id = getattr(settings, "gcp_project_id", None)
        location = provider_spec.google_location or getattr(settings, "gcp_region", None)
        if not project_id or not location:
            raise ValueError(
                "Google provider requires GCP_PROJECT_ID and GCP_REGION or COPILOT_GOOGLE_LOCATION."
            )

        return ChatGoogleGenerativeAI(
            model=provider_spec.model_name,
            vertexai=True,
            project=project_id,
            location=location,
            temperature=temperature,
            max_tokens=max_tokens,
            retries=0,
            disable_streaming="tool_calling",
        )

    if provider_spec.provider_family == "openai":
        from langchain_openai import ChatOpenAI

        if getattr(settings, "openai_api_key", None):
            os.environ.setdefault("OPENAI_API_KEY", str(settings.openai_api_key))

        return ChatOpenAI(
            model=provider_spec.model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=0,
            stream_usage=True,
        )

    if provider_spec.provider_family == "anthropic":
        from langchain_anthropic import ChatAnthropic

        if getattr(settings, "anthropic_api_key", None):
            os.environ.setdefault(
                "ANTHROPIC_API_KEY", str(settings.anthropic_api_key)
            )

        return ChatAnthropic(
            model=provider_spec.model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=0,
            stream_usage=True,
        )

    raise ValueError(f"Unsupported provider family: {provider_spec.provider_family}")


__all__ = [
    "LlmProviderSpec",
    "ProviderFamily",
    "build_langchain_chat_model",
    "resolve_runtime_provider_specs",
]