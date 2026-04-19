from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

from dotenv import load_dotenv

from app.llm.providers import (
    LlmProviderSpec,
    ProviderFamily,
    build_langchain_chat_model,
    resolve_runtime_provider_specs,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env.local", override=False)
load_dotenv(PROJECT_ROOT / ".env", override=False)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

@dataclass(frozen=True, slots=True)
class EvalProviderSpec:
    provider_id: str
    label: str
    provider_family: ProviderFamily
    planner_model: str
    patch_model: str
    # Some Vertex preview models are only reachable through `global`, while
    # stable Gemini 2.5 models remain available in a regional endpoint.
    google_location: str | None = None


DEFAULT_PROMPTFOO_PROVIDER_SPECS: tuple[EvalProviderSpec, ...] = (
    EvalProviderSpec(
        provider_id="openai-gpt-5.4-mini",
        label="openai-gpt-5.4-mini",
        provider_family="openai",
        planner_model="gpt-5.4-mini",
        patch_model="gpt-5.4-mini",
    ),
    EvalProviderSpec(
        provider_id="openai-gpt-5.4-nano",
        label="openai-gpt-5.4-nano",
        provider_family="openai",
        planner_model="gpt-5.4-nano",
        patch_model="gpt-5.4-nano",
    ),
    EvalProviderSpec(
        provider_id="google-gemini-2.5-flash",
        label="google-gemini-2.5-flash",
        provider_family="google",
        planner_model="gemini-2.5-flash",
        patch_model="gemini-2.5-flash",
        google_location="us-east1",
    ),
    EvalProviderSpec(
        provider_id="google-gemini-2.5-flash-lite",
        label="google-gemini-2.5-flash-lite",
        provider_family="google",
        planner_model="gemini-2.5-flash-lite",
        patch_model="gemini-2.5-flash-lite",
        google_location="us-east1",
    ),
    EvalProviderSpec(
        provider_id="google-gemini-3-flash-preview",
        label="google-gemini-3-flash-preview",
        provider_family="google",
        planner_model="gemini-3-flash-preview",
        patch_model="gemini-3-flash-preview",
        google_location="global",
    ),
    EvalProviderSpec(
        provider_id="google-gemini-3.1-flash-lite-preview",
        label="google-gemini-3.1-flash-lite-preview",
        provider_family="google",
        planner_model="gemini-3.1-flash-lite-preview",
        patch_model="gemini-3.1-flash-lite-preview",
        google_location="global",
    ),
    EvalProviderSpec(
        provider_id="anthropic-claude-haiku-4-5",
        label="anthropic-claude-haiku-4-5",
        provider_family="anthropic",
        planner_model="claude-haiku-4-5",
        patch_model="claude-haiku-4-5",
    ),
)


def all_promptfoo_provider_specs() -> tuple[EvalProviderSpec, ...]:
    return DEFAULT_PROMPTFOO_PROVIDER_SPECS


def missing_live_eval_env() -> list[str]:
    settings = _build_settings(os.getenv("VERTEX_MODEL") or "gemini-2.5-flash")
    planner_spec, patch_spec = resolve_runtime_provider_specs(settings)
    missing: list[str] = []
    for provider_family in {
        planner_spec.provider_family,
        patch_spec.provider_family,
    }:
        missing.extend(missing_promptfoo_eval_env(provider_family))
    return list(dict.fromkeys(missing))


def missing_promptfoo_eval_env(provider_family: ProviderFamily) -> list[str]:
    if provider_family == "google":
        return missing_live_eval_env()
    if provider_family == "openai":
        return [] if os.getenv("OPENAI_API_KEY") else ["OPENAI_API_KEY"]
    if provider_family == "anthropic":
        return [] if os.getenv("ANTHROPIC_API_KEY") else ["ANTHROPIC_API_KEY"]
    raise ValueError(f"Unsupported eval provider family: {provider_family}")


def resolve_promptfoo_provider_config(
    *,
    options: Mapping[str, Any] | None,
    context: Mapping[str, Any] | None,
) -> dict[str, Any]:
    provider_config = dict((options or {}).get("config") or {})
    for source in (options or {}, context or {}):
        for key in (
            "provider_id",
            "label",
            "provider_family",
            "planner_model",
            "patch_model",
            "google_location",
        ):
            if key in source and key not in provider_config:
                provider_config[key] = source[key]

    provider_config.setdefault("provider_family", "google")
    provider_config.setdefault(
        "planner_model",
        provider_config.get("patch_model")
        or os.getenv("VERTEX_MODEL")
        or "gemini-2.5-flash",
    )
    provider_config.setdefault("patch_model", provider_config["planner_model"])
    provider_config.setdefault(
        "provider_id",
        provider_config.get("label")
        or f"{provider_config['provider_family']}-{provider_config['planner_model']}",
    )
    provider_config.setdefault("label", provider_config["provider_id"])
    return provider_config


def promptfoo_provider_dicts() -> list[dict[str, Any]]:
    return [
        {
            "id": "file://provider.py",
            "label": spec.label,
            "config": {
                "workers": 1,
                "provider_id": spec.provider_id,
                "provider_family": spec.provider_family,
                "planner_model": spec.planner_model,
                "patch_model": spec.patch_model,
                "google_location": spec.google_location,
            },
        }
        for spec in DEFAULT_PROMPTFOO_PROVIDER_SPECS
    ]


def _build_settings(default_vertex_model: str, google_location: str | None = None) -> Any:
    return SimpleNamespace(
        gcp_project_id=os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT"),
        gcp_region=google_location
        or os.getenv("GCP_REGION")
        or os.getenv("GOOGLE_CLOUD_LOCATION")
        or "us-east1",
        vertex_model=default_vertex_model,
        llm_provider_family=os.getenv("COPILOT_LLM_PROVIDER_FAMILY", "openai"),
        planner_provider_family=os.getenv("COPILOT_PLANNER_PROVIDER_FAMILY"),
        planner_model=os.getenv("COPILOT_PLANNER_MODEL"),
        patch_provider_family=os.getenv("COPILOT_PATCH_PROVIDER_FAMILY"),
        patch_model=os.getenv("COPILOT_PATCH_MODEL"),
        google_location=os.getenv("COPILOT_GOOGLE_LOCATION"),
        planner_google_location=os.getenv("COPILOT_PLANNER_GOOGLE_LOCATION"),
        patch_google_location=os.getenv("COPILOT_PATCH_GOOGLE_LOCATION"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
    )


def build_live_planner_from_env() -> Any:
    from app.planner import LangChainCopilotPlanner

    missing = missing_live_eval_env()
    if missing:
        raise RuntimeError(
            "Missing environment for live copilot evals: " + ", ".join(missing)
        )

    return LangChainCopilotPlanner(
        settings=_build_settings(os.getenv("VERTEX_MODEL") or "gemini-2.5-flash")
    )


def build_promptfoo_planner(provider_config: Mapping[str, Any]) -> Any:
    from app.planner import LangChainCopilotPlanner

    provider_family = provider_config["provider_family"]
    missing = missing_promptfoo_eval_env(provider_family)
    if missing:
        raise RuntimeError(
            "Missing environment for promptfoo provider "
            f"{provider_config['provider_id']}: {', '.join(missing)}"
        )

    return LangChainCopilotPlanner(
        settings=_build_settings(
            provider_config["planner_model"],
            google_location=provider_config.get("google_location"),
        ),
        _planner_model=build_langchain_chat_model(
            settings=_build_settings(
                provider_config["planner_model"],
                google_location=provider_config.get("google_location"),
            ),
            provider_spec=LlmProviderSpec(
                provider_family=provider_family,
                model_name=provider_config["planner_model"],
                google_location=provider_config.get("google_location"),
            ),
            temperature=0.1,
            max_tokens=1400,
        ),
        _patch_model=build_langchain_chat_model(
            settings=_build_settings(
                provider_config["patch_model"],
                google_location=provider_config.get("google_location"),
            ),
            provider_spec=LlmProviderSpec(
                provider_family=provider_family,
                model_name=provider_config["patch_model"],
                google_location=provider_config.get("google_location"),
            ),
            temperature=0.0,
            max_tokens=3200,
        ),
    )


def build_propose_replace_span_tool() -> Any:
    from langchain_core.tools import tool

    from app.graph.tools import ProposePatchInput

    @tool("propose_replace_span", args_schema=ProposePatchInput)
    def propose_replace_span_stub(
        target_document_id: str,
        instruction: str | None = None,
    ) -> str:
        """Stub schema used to evaluate the live planner tool contract."""
        del target_document_id, instruction
        return "not executed in eval"

    return propose_replace_span_stub


def build_set_edit_plan_tool() -> Any:
    from langchain_core.tools import tool

    from app.planner import ClinicalPlan

    @tool("set_edit_plan", args_schema=ClinicalPlan)
    def set_edit_plan_stub(
        edit_scope: str,
        clinical_impact_level: str,
        affected_sections: list[str],
        needs_full_note: bool,
        needs_external_knowledge: bool,
        factual_replacements: list[dict[str, object]] | None = None,
    ) -> str:
        """Stub schema used to evaluate the live planner clinical classification contract."""
        del (
            edit_scope,
            clinical_impact_level,
            affected_sections,
            needs_full_note,
            needs_external_knowledge,
            factual_replacements,
        )
        return "not executed in eval"

    return set_edit_plan_stub


def normalize_message_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return str(content)


def normalize_tool_calls(tool_calls: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for tool_call in tool_calls or []:
        normalized.append(
            {
                "id": tool_call.get("id"),
                "name": tool_call.get("name"),
                "args": tool_call.get("args") or {},
            }
        )
    return normalized


def drafted_plan_to_payload(plan: Any) -> dict[str, Any]:
    return plan.model_dump(mode="python", by_alias=True, exclude_none=True)