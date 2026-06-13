from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache

from groq import BadRequestError, Groq
from openai import OpenAI

from common.llm_response import LlmResponse, build_llm_response_from_message

logger = logging.getLogger(__name__)

DEFAULT_GROQ_REASONING_EFFORT_QWEN = "default"
DEFAULT_GROQ_REASONING_FORMAT_QWEN = "parsed"
DEFAULT_GROQ_REASONING_EFFORT_GPT_OSS = "medium"
GROQ_QWEN_REASONING_EFFORTS = frozenset({"none", "default"})
GROQ_GPT_OSS_REASONING_EFFORTS = frozenset({"low", "medium", "high"})
GROQ_QWEN_REASONING_FORMATS = frozenset({"raw", "parsed", "hidden"})

OPENAI_REASONING_EFFORT_CHOICES = (
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
)
DEFAULT_OPENAI_REASONING_EFFORT = "none"
OPENAI_REASONING_EFFORT_ENV = "OPENAI_REASONING_EFFORT"

ALLOWED_PROVIDERS = ("openai", "groq", "gemini", "anthropic")
PROVIDER_ALIASES = {"google": "gemini"}

DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
DEFAULT_GROQ_MODEL = "qwen/qwen3-32b"
GROQ_MODEL_CHOICES = (
    "qwen/qwen3-32b",
    "openai/gpt-oss-20b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
)
GROQ_CUSTOM_MODEL_LABEL = "Otro (escribir)"
DEFAULT_GEMINI_MODEL = "gemini-3-flash-preview"
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"

DEFAULT_MODEL_BY_PROVIDER: dict[str, str] = {
    "openai": DEFAULT_OPENAI_MODEL,
    "groq": DEFAULT_GROQ_MODEL,
    "gemini": DEFAULT_GEMINI_MODEL,
    "anthropic": DEFAULT_ANTHROPIC_MODEL,
}

DEFAULT_MODEL_ENV_BY_PROVIDER: dict[str, str] = {
    "openai": "OPENAI_MODEL",
    "groq": "GROQ_MODEL",
    "gemini": "GEMINI_MODEL",
    "anthropic": "ANTHROPIC_MODEL",
}


@dataclass(frozen=True, slots=True)
class ModelSpec:
    alias: str
    provider: str
    model: str


@dataclass(frozen=True, slots=True)
class ProviderRuntimeConfig:
    provider: str
    max_output_param: str
    default_max_output_tokens: int
    max_output_env_var: str
    json_mode_env_var: str
    default_json_mode: bool


PROVIDER_RUNTIME_CONFIGS: dict[str, ProviderRuntimeConfig] = {
    "openai": ProviderRuntimeConfig(
        provider="openai",
        max_output_param="max_completion_tokens",
        default_max_output_tokens=16_384,
        max_output_env_var="OPENAI_MAX_COMPLETION_TOKENS",
        json_mode_env_var="OPENAI_JSON_MODE",
        default_json_mode=True,
    ),
    "groq": ProviderRuntimeConfig(
        provider="groq",
        max_output_param="max_tokens",
        default_max_output_tokens=16_384,
        max_output_env_var="GROQ_MAX_TOKENS",
        json_mode_env_var="GROQ_JSON_MODE",
        default_json_mode=True,
    ),
    "gemini": ProviderRuntimeConfig(
        provider="gemini",
        max_output_param="max_output_tokens",
        default_max_output_tokens=16_384,
        max_output_env_var="GEMINI_MAX_OUTPUT_TOKENS",
        json_mode_env_var="GEMINI_JSON_MODE",
        default_json_mode=True,
    ),
    "anthropic": ProviderRuntimeConfig(
        provider="anthropic",
        max_output_param="max_tokens",
        default_max_output_tokens=16_384,
        max_output_env_var="ANTHROPIC_MAX_TOKENS",
        json_mode_env_var="ANTHROPIC_JSON_MODE",
        default_json_mode=True,
    ),
}


def normalize_provider_name(raw: str) -> str:
    normalized = raw.strip().lower()
    return PROVIDER_ALIASES.get(normalized, normalized)


def provider_runtime_config(provider: str) -> ProviderRuntimeConfig:
    normalized = normalize_provider_name(provider)
    config = PROVIDER_RUNTIME_CONFIGS.get(normalized)
    if config is None:
        raise ValueError(
            f"ai_pipeline_provider_not_allowed: {normalized!r} "
            f"(allowed: {', '.join(ALLOWED_PROVIDERS)})"
        )
    return config


def default_model_for_provider(provider: str) -> str:
    normalized = normalize_provider_name(provider)
    provider_runtime_config(normalized)
    env_name = DEFAULT_MODEL_ENV_BY_PROVIDER[normalized]
    return os.environ.get(env_name, DEFAULT_MODEL_BY_PROVIDER[normalized]).strip()


def parse_model_specs(raw: str) -> list[ModelSpec]:
    specs: list[ModelSpec] = []
    for item in raw.split(","):
        normalized = item.strip()
        if not normalized:
            continue
        provider, sep, model = normalized.partition(":")
        if not sep or not provider.strip() or not model.strip():
            raise ValueError(
                "Invalid model spec. Expected provider:model, for example "
                "openai:gpt-5.4-mini"
            )
        provider_name = normalize_provider_name(provider)
        provider_runtime_config(provider_name)
        specs.append(
            ModelSpec(
                alias=provider_name,
                provider=provider_name,
                model=model.strip(),
            )
        )
    if not specs:
        raise ValueError("At least one model spec is required")
    return specs


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"ai_pipeline_missing_env: {name}")
    return value


def _require_api_key(provider: str) -> str:
    env_by_provider = {
        "openai": "OPENAI_API_KEY",
        "groq": "GROQ_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
    }
    env_name = env_by_provider.get(provider)
    if env_name is None:
        raise ValueError(f"ai_pipeline_provider_has_no_api_key: {provider}")
    return _require_env(env_name)


def _env_int(name: str, fallback: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return fallback
    return int(raw)


def _env_bool(name: str, fallback: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return fallback
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return fallback


def _resolve_max_output_tokens(config: ProviderRuntimeConfig) -> int:
    primary = _env_int(config.max_output_env_var, 0)
    if primary > 0:
        return primary
    if config.provider == "openai":
        legacy = _env_int("OPENAI_MAX_TOKENS", 0)
        if legacy > 0:
            return legacy
    return config.default_max_output_tokens


def _json_mode_enabled(config: ProviderRuntimeConfig) -> bool:
    if config.provider == "groq":
        raw = os.environ.get(config.json_mode_env_var, "auto").strip().lower()
        if raw == "auto":
            return True
        return _env_bool(config.json_mode_env_var, config.default_json_mode)
    return _env_bool(config.json_mode_env_var, config.default_json_mode)


def _completion_limit_kwargs(config: ProviderRuntimeConfig) -> dict[str, int]:
    return {config.max_output_param: _resolve_max_output_tokens(config)}


def _gemini_location(model: str) -> str:
    for env_name in ("GEMINI_LOCATION", "GCP_REGION", "VERTEX_AI_LOCATION"):
        value = os.environ.get(env_name, "").strip()
        if value:
            return value
    normalized = model.lower()
    if "preview" in normalized or normalized.startswith("gemini-3"):
        return "global"
    return "us-east1"


@lru_cache(maxsize=4)
def _get_gemini_client(project_id: str, location: str):
    from google import genai

    return genai.Client(vertexai=True, project=project_id, location=location)


def _groq_error_detail(exc: BadRequestError) -> str:
    body = getattr(exc, "body", None)
    if not isinstance(body, dict):
        return str(exc)
    error = body.get("error")
    if not isinstance(error, dict):
        return str(exc)
    message = error.get("message", str(exc))
    code = error.get("code")
    failed_generation = error.get("failed_generation")
    parts = [message]
    if code:
        parts.append(f"code={code}")
    if failed_generation:
        parts.append(f"failed_generation={failed_generation!r}")
    return " | ".join(parts)


def _is_groq_json_validate_error(exc: BadRequestError) -> bool:
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and error.get("code") == "json_validate_failed":
            return True
    return "json_validate_failed" in str(exc)


def _groq_model_family(model: str) -> str | None:
    normalized = model.lower()
    if "qwen3" in normalized:
        return "qwen3"
    if "gpt-oss" in normalized:
        return "gpt-oss"
    if "deepseek-r1" in normalized or "deepseek/r1" in normalized:
        return "deepseek-r1"
    return None


def openai_model_supports_reasoning_effort(model: str) -> bool:
    normalized = model.strip().lower()
    return normalized == "gpt-5.4" or normalized.startswith("gpt-5.4-")


def _resolve_openai_reasoning_effort(
    model: str,
) -> tuple[dict[str, object], dict[str, object]]:
    if not openai_model_supports_reasoning_effort(model):
        return {}, {}

    effort = os.environ.get(
        OPENAI_REASONING_EFFORT_ENV,
        DEFAULT_OPENAI_REASONING_EFFORT,
    ).strip().lower()
    if effort not in OPENAI_REASONING_EFFORT_CHOICES or effort == "none":
        return {}, {}

    api_kwargs: dict[str, object] = {"reasoning_effort": effort}
    request_metadata: dict[str, object] = {"reasoning_effort": effort}
    return api_kwargs, request_metadata


def _resolve_groq_reasoning_kwargs(
    model: str,
) -> tuple[dict[str, object], dict[str, object]]:
    family = _groq_model_family(model)
    if family is None:
        return {}, {}

    request_metadata: dict[str, object] = {"model_family": family}
    api_kwargs: dict[str, object] = {}

    if family == "qwen3":
        effort = os.environ.get(
            "GROQ_REASONING_EFFORT",
            DEFAULT_GROQ_REASONING_EFFORT_QWEN,
        ).strip().lower()
        if effort not in GROQ_QWEN_REASONING_EFFORTS:
            effort = DEFAULT_GROQ_REASONING_EFFORT_QWEN

        reasoning_format = os.environ.get(
            "GROQ_REASONING_FORMAT",
            DEFAULT_GROQ_REASONING_FORMAT_QWEN,
        ).strip().lower()
        if reasoning_format not in GROQ_QWEN_REASONING_FORMATS:
            reasoning_format = DEFAULT_GROQ_REASONING_FORMAT_QWEN

        api_kwargs["reasoning_effort"] = effort
        api_kwargs["reasoning_format"] = reasoning_format
        request_metadata["reasoning_effort"] = effort
        request_metadata["reasoning_format"] = reasoning_format
        return api_kwargs, request_metadata

    if family == "gpt-oss":
        effort = os.environ.get(
            "GROQ_REASONING_EFFORT",
            DEFAULT_GROQ_REASONING_EFFORT_GPT_OSS,
        ).strip().lower()
        if effort not in GROQ_GPT_OSS_REASONING_EFFORTS:
            effort = DEFAULT_GROQ_REASONING_EFFORT_GPT_OSS
        api_kwargs["reasoning_effort"] = effort
        request_metadata["reasoning_effort"] = effort
        return api_kwargs, request_metadata

    reasoning_format = os.environ.get("GROQ_REASONING_FORMAT", "").strip().lower()
    if reasoning_format in GROQ_QWEN_REASONING_FORMATS:
        api_kwargs["reasoning_format"] = reasoning_format
        request_metadata["reasoning_format"] = reasoning_format
    return api_kwargs, request_metadata


def _anthropic_message_text(response: object) -> str:
    content = getattr(response, "content", None)
    if not isinstance(content, list):
        raise ValueError("ai_pipeline_anthropic_empty_response")
    for block in content:
        if getattr(block, "type", None) == "text":
            text = getattr(block, "text", "") or ""
            if text.strip():
                return text
    raise ValueError("ai_pipeline_anthropic_empty_response")


def _call_groq(
    *,
    client: Groq,
    config: ProviderRuntimeConfig,
    model: str,
    system: str,
    user: str,
    json_mode: bool,
) -> LlmResponse:
    reasoning_kwargs, request_metadata = _resolve_groq_reasoning_kwargs(model)
    kwargs: dict[str, object] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0,
        **_completion_limit_kwargs(config),
        **reasoning_kwargs,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    response = client.chat.completions.create(**kwargs)
    return build_llm_response_from_message(
        message=response.choices[0].message,
        usage=response.usage,
        request_params=request_metadata,
        provider="groq",
    )


def _ensure_openai_json_input_hint(text: str) -> str:
    if "json" in text.lower():
        return text
    return f"{text}\n\nRespond with a valid JSON object."


def _call_openai_responses(
    *,
    client: OpenAI,
    config: ProviderRuntimeConfig,
    model: str,
    system: str,
    user: str,
    json_mode: bool,
    request_metadata: dict[str, object],
) -> LlmResponse:
    from common.llm_response import build_llm_response_from_openai_responses

    effort = request_metadata.get("reasoning_effort")
    resolved_user = _ensure_openai_json_input_hint(user) if json_mode else user
    kwargs: dict[str, object] = {
        "model": model,
        "instructions": system,
        "input": resolved_user,
        "max_output_tokens": _resolve_max_output_tokens(config),
        "reasoning": {"effort": effort, "summary": "auto"},
    }
    if json_mode:
        kwargs["text"] = {"format": {"type": "json_object"}}
    response = client.responses.create(**kwargs)
    return build_llm_response_from_openai_responses(
        response=response,
        request_params=request_metadata,
    )


def _call_openai(
    *,
    client: OpenAI,
    config: ProviderRuntimeConfig,
    model: str,
    system: str,
    user: str,
    json_mode: bool,
) -> LlmResponse:
    reasoning_kwargs, request_metadata = _resolve_openai_reasoning_effort(model)
    if reasoning_kwargs:
        return _call_openai_responses(
            client=client,
            config=config,
            model=model,
            system=system,
            user=user,
            json_mode=json_mode,
            request_metadata=request_metadata,
        )

    kwargs: dict[str, object] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        **_completion_limit_kwargs(config),
        **reasoning_kwargs,
    }
    if "reasoning_effort" not in kwargs:
        kwargs["temperature"] = 0
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    response = client.chat.completions.create(**kwargs)
    return build_llm_response_from_message(
        message=response.choices[0].message,
        usage=response.usage,
        request_params=request_metadata,
        provider="openai",
    )


def _call_gemini(
    *,
    config: ProviderRuntimeConfig,
    model: str,
    system: str,
    user: str,
    json_mode: bool,
) -> LlmResponse:
    from google.genai import types

    project_id = _require_env("GCP_PROJECT_ID")
    client = _get_gemini_client(project_id, _gemini_location(model))
    generate_config = types.GenerateContentConfig(
        system_instruction=system,
        temperature=0,
        candidate_count=1,
        max_output_tokens=_resolve_max_output_tokens(config),
    )
    if json_mode:
        generate_config.response_mime_type = "application/json"
    response = client.models.generate_content(
        model=model,
        contents=[user],
        config=generate_config,
    )
    content = getattr(response, "text", "") or ""
    if not content.strip():
        raise ValueError("ai_pipeline_gemini_empty_response")
    return LlmResponse(content=content)


def _call_anthropic(
    *,
    config: ProviderRuntimeConfig,
    model: str,
    system: str,
    user: str,
) -> LlmResponse:
    from anthropic import Anthropic

    client = Anthropic(api_key=_require_api_key("anthropic"))
    response = client.messages.create(
        model=model,
        max_tokens=_resolve_max_output_tokens(config),
        temperature=0,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    content = _anthropic_message_text(response)
    return LlmResponse(content=content)


def call_llm_detailed(
    *, provider: str, model: str, system: str, user: str
) -> LlmResponse:
    config = provider_runtime_config(provider)
    json_mode = _json_mode_enabled(config)

    if config.provider == "openai":
        client = OpenAI(api_key=_require_api_key("openai"))
        return _call_openai(
            client=client,
            config=config,
            model=model,
            system=system,
            user=user,
            json_mode=json_mode,
        )

    if config.provider == "gemini":
        return _call_gemini(
            config=config,
            model=model,
            system=system,
            user=user,
            json_mode=json_mode,
        )

    if config.provider == "anthropic":
        return _call_anthropic(
            config=config,
            model=model,
            system=system,
            user=user,
        )

    client = Groq(api_key=_require_api_key("groq"))
    if not json_mode:
        return _call_groq(
            client=client,
            config=config,
            model=model,
            system=system,
            user=user,
            json_mode=False,
        )

    try:
        return _call_groq(
            client=client,
            config=config,
            model=model,
            system=system,
            user=user,
            json_mode=True,
        )
    except BadRequestError as exc:
        if not _is_groq_json_validate_error(exc):
            raise ValueError(
                f"ai_pipeline_groq_error: {_groq_error_detail(exc)}"
            ) from exc
        logger.warning(
            "groq json_object failed for model=%s (%s); retry plain",
            model,
            _groq_error_detail(exc),
        )
        return _call_groq(
            client=client,
            config=config,
            model=model,
            system=system,
            user=user,
            json_mode=False,
        )


def call_llm(*, provider: str, model: str, system: str, user: str) -> str:
    return call_llm_detailed(
        provider=provider,
        model=model,
        system=system,
        user=user,
    ).content


__all__ = [
    "ALLOWED_PROVIDERS",
    "DEFAULT_OPENAI_REASONING_EFFORT",
    "DEFAULT_MODEL_BY_PROVIDER",
    "GROQ_CUSTOM_MODEL_LABEL",
    "GROQ_MODEL_CHOICES",
    "ModelSpec",
    "OPENAI_REASONING_EFFORT_CHOICES",
    "OPENAI_REASONING_EFFORT_ENV",
    "call_llm",
    "call_llm_detailed",
    "default_model_for_provider",
    "normalize_provider_name",
    "openai_model_supports_reasoning_effort",
    "parse_model_specs",
    "provider_runtime_config",
]
