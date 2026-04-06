from __future__ import annotations

import time

import pytest
from langsmith import testing as t

from evals.shared.clinical_reasoning_cases import (
    all_clinical_reasoning_cases,
    build_reasoning_conv_history,
    build_reasoning_eval_state,
)
from evals.shared.live_eval_support import (
    EvalProviderSpec,
    build_promptfoo_planner,
    build_set_edit_plan_tool,
    missing_promptfoo_eval_env,
    normalize_message_content,
    normalize_tool_calls,
)


# Flip these booleans to compare only the providers you care about for this
# qualitative reasoning surface. `gpt-4o-mini` is used here as the closest
# practical OpenAI "GPT-4 mini" model id for local provider comparisons.
ENABLE_GEMINI_3_FLASH_PREVIEW = True
ENABLE_CLAUDE_HAIKU_4_5 = True
ENABLE_GPT_4_MINI = True


def _enabled_provider_specs() -> tuple[EvalProviderSpec, ...]:
    providers: list[EvalProviderSpec] = []
    if ENABLE_GEMINI_3_FLASH_PREVIEW:
        providers.append(
            EvalProviderSpec(
                provider_id="google-gemini-3-flash-preview",
                label="google-gemini-3-flash-preview",
                provider_family="google",
                planner_model="gemini-3-flash-preview",
                patch_model="gemini-3-flash-preview",
                google_location="global",
            )
        )
    if ENABLE_CLAUDE_HAIKU_4_5:
        providers.append(
            EvalProviderSpec(
                provider_id="anthropic-claude-haiku-4-5",
                label="anthropic-claude-haiku-4-5",
                provider_family="anthropic",
                planner_model="claude-haiku-4-5",
                patch_model="claude-haiku-4-5",
            )
        )
    if ENABLE_GPT_4_MINI:
        providers.append(
            EvalProviderSpec(
                provider_id="openai-gpt-5.4-mini",
                label="openai-gpt-5.4-mini",
                provider_family="openai",
                planner_model="gpt-5.4-mini",
                patch_model="gpt-5.4-mini",
            )
        )
    return tuple(providers)


def _provider_param_values() -> list[object]:
    return [
        pytest.param(
            spec,
            id=spec.provider_id,
        )
        for spec in _enabled_provider_specs()
    ]


def _provider_config(spec: EvalProviderSpec) -> dict[str, str]:
    return {
        "provider_id": spec.provider_id,
        "label": spec.label,
        "provider_family": spec.provider_family,
        "planner_model": spec.planner_model,
        "patch_model": spec.patch_model,
        "google_location": spec.google_location or "",
    }


@pytest.mark.live_llm
@pytest.mark.langsmith
@pytest.mark.parametrize("provider_spec", _provider_param_values())
@pytest.mark.parametrize(
    "case",
    all_clinical_reasoning_cases(),
    ids=lambda case: case.slug,
)
def test_live_clinical_reasoning_cases(provider_spec, case) -> None:
    missing = missing_promptfoo_eval_env(provider_spec.provider_family)
    if missing:
        pytest.skip(
            f"Missing env for {provider_spec.provider_id}: {', '.join(missing)}"
        )

    planner = build_promptfoo_planner(_provider_config(provider_spec))
    state = build_reasoning_eval_state(case)
    tools = [build_set_edit_plan_tool()]

    # Full LangGraph-style conversation history: doctor message -> LLM reads doc -> doc content.
    # The planner is called at this point and must reason clinically without re-reading.
    conv_history = build_reasoning_conv_history(case)

    t.log_inputs(
        {
            "case_slug": case.slug,
            "case_level": case.level,
            "case_title": case.title,
            "provider": provider_spec.provider_id,
            "provider_family": provider_spec.provider_family,
            "planner_model": provider_spec.planner_model,
            "doctor_message": case.doctor_message,
            "target_document_id": case.target_document_id,
            "selected_document_ids": list(case.selected_document_ids),
            "what_it_tests": list(case.what_it_tests),
        }
    )

    started_at = time.monotonic()
    response = planner.invoke_model(
        state=state,
        messages=conv_history,
        tools=tools,
    )
    planner_latency = time.monotonic() - started_at

    tool_calls = normalize_tool_calls(getattr(response, "tool_calls", None))
    first_tool = tool_calls[0] if tool_calls else None
    set_edit_plan_args: dict | None = first_tool.get("args") if first_tool and first_tool.get("name") == "set_edit_plan" else None
    planner_reasoning = normalize_message_content(response.content)

    t.log_outputs(
        {
            # Leading columns visible in LangSmith without opening each trace.
            "model_name": provider_spec.planner_model,
            "difficulty": case.level,
            "planner_latency_s": round(planner_latency, 2),
            # Clinical reasoning: what the model said / thought before deciding.
            "planner_reasoning": planner_reasoning,
            # set_edit_plan classification: scope, sections, impact level.
            "called_set_edit_plan": first_tool.get("name") == "set_edit_plan" if first_tool else False,
            "edit_scope": (set_edit_plan_args or {}).get("edit_scope"),
            "clinical_impact_level": (set_edit_plan_args or {}).get("clinical_impact_level"),
            "affected_sections": list((set_edit_plan_args or {}).get("affected_sections") or []),
            "needs_full_note": (set_edit_plan_args or {}).get("needs_full_note"),
        }
    )
    t.log_feedback(
        key="produced_output",
        score=float(bool(tool_calls) or bool(planner_reasoning)),
    )
    t.log_feedback(
        key="called_set_edit_plan",
        score=float(set_edit_plan_args is not None),
    )

    assert tool_calls or planner_reasoning, (
        f"{provider_spec.provider_id} produced neither tool calls nor text for {case.slug}."
    )
