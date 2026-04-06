"""End-to-end multi-provider eval: planner → drafter pipeline.

Each test case gives the planner BOTH tools (set_edit_plan + propose_replace_span)
and lets it decide the full plan-then-draft flow, just like production.

Parametrized over provider × clinical case so LangSmith results are directly
comparable across models.

Run all providers:
    make evals-e2e

Run one provider:
    make evals-e2e-model MODEL=google-gemini-2.5-flash
"""

from __future__ import annotations

import time

import pytest
from langsmith import testing as t

import app.planner as planner_module
from app.graph.tools import _validate_drafted_plan_against_clinical_plan
from evals.shared.clinical_cases import (
    LiveClinicalCase,
    all_live_clinical_cases,
    build_clinical_plan,
    build_eval_state,
    build_target_document,
)
from evals.shared.live_eval_support import (
    EvalProviderSpec,
    all_promptfoo_provider_specs,
    build_promptfoo_planner,
    build_propose_replace_span_tool,
    build_set_edit_plan_tool,
    drafted_plan_to_payload,
    missing_promptfoo_eval_env,
    normalize_message_content,
    normalize_tool_calls,
)


def _provider_param_values() -> list[object]:
    return [
        pytest.param(
            spec,
            spec.provider_id,
            spec.planner_model,
            spec.patch_model,
            spec.google_location or "n/a",
            id=spec.provider_id,
        )
        for spec in all_promptfoo_provider_specs()
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


def _extract_clinical_plan_from_tool_call(
    tool_args: dict,
) -> dict:
    """Build a clinical_plan dict from the set_edit_plan tool call args."""
    return {
        "edit_scope": str(tool_args.get("edit_scope") or "propagation"),
        "clinical_impact_level": str(
            tool_args.get("clinical_impact_level") or "clinical"
        ),
        "affected_sections": [
            str(s).strip().lower().replace(" ", "_")
            for s in (tool_args.get("affected_sections") or [])
        ],
        "needs_full_note": bool(tool_args.get("needs_full_note", True)),
        "needs_external_knowledge": bool(
            tool_args.get("needs_external_knowledge", False)
        ),
    }


@pytest.mark.live_llm
@pytest.mark.langsmith
@pytest.mark.parametrize(
    "provider_spec,provider_id,model_name,patch_model_name,provider_region",
    _provider_param_values(),
)
@pytest.mark.parametrize(
    "case",
    all_live_clinical_cases(),
    ids=lambda case: case.slug,
)
def test_e2e_planner_drafter_pipeline(
    provider_spec: EvalProviderSpec,
    provider_id: str,
    model_name: str,
    patch_model_name: str,
    provider_region: str,
    case: LiveClinicalCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full pipeline: give the planner ALL tools, let it plan, then draft patches.

    Hard assertions (test fails):
    - Planner calls exactly one tool on the first turn.
    - Planner picks set_edit_plan for propagation/reinterpretation cases.
    - Drafter produces at least one patch.
    - Drafter passes runtime validation (sections complete).
    - No runtime errors.

    Soft feedback (LangSmith scores for comparison):
    - edit_scope / clinical_impact_level exact match vs. gold label
    - Section coverage completeness
    - Patch count relative to expected sections
    - Latency
    """
    missing = missing_promptfoo_eval_env(provider_spec.provider_family)
    if missing:
        pytest.skip(
            f"Missing env for {provider_id}: {', '.join(missing)}"
        )

    planner = build_promptfoo_planner(_provider_config(provider_spec))
    state = build_eval_state(case)
    target_document = build_target_document(case)
    all_tools = [build_set_edit_plan_tool(), build_propose_replace_span_tool()]

    raw_message_holder: dict[str, object] = {}

    def _capture_raw_tool_calls(message):
        raw_message_holder["message"] = message
        return message

    monkeypatch.setattr(
        planner_module,
        "_filter_parallel_tool_calls",
        _capture_raw_tool_calls,
    )

    t.log_inputs(
        {
            # Keep high-signal comparison fields at the top so LangSmith tables let
            # us filter by model/family/region without opening every individual run.
            "model_name": model_name,
            "patch_model_name": patch_model_name,
            "provider": provider_id,
            "provider_family": provider_spec.provider_family,
            "provider_region": provider_region,
            "case_slug": case.slug,
            "edit_scope": case.edit_scope,
            "clinical_impact_level": case.clinical_impact_level,
            "user_message": case.user_message,
            "target_document_id": case.target_document_id,
            "selected_document_ids": state.get("selected_document_ids") or [],
            "affected_sections": list(case.affected_sections),
            "document_excerpt": case.target_document_content[:900],
        }
    )
    t.log_reference_outputs(
        {
            "model_name": model_name,
            "expected_edit_scope": case.edit_scope,
            "expected_clinical_impact_level": case.clinical_impact_level,
            "expected_affected_sections": list(case.affected_sections),
            "expected_min_patches": len(case.affected_sections),
        }
    )

    # ── Step 1: Planner first turn (with ALL tools) ──────────────────────
    t0 = time.monotonic()
    planner_response = planner.invoke_model(
        state=state,
        messages=state["messages"],
        tools=all_tools,
    )
    planner_latency = time.monotonic() - t0

    raw_message = raw_message_holder.get("message") or planner_response
    raw_tool_calls = normalize_tool_calls(
        getattr(raw_message, "tool_calls", None)
    )
    first_call = raw_tool_calls[0] if raw_tool_calls else {}
    first_call_name = first_call.get("name", "")
    first_call_args = first_call.get("args", {})

    # ── Step 2: Resolve clinical plan ────────────────────────────────────
    requires_edit_plan = case.edit_scope in {"propagation", "reinterpretation"}

    if first_call_name == "set_edit_plan":
        # Model decided to plan first — extract its plan
        model_clinical_plan = _extract_clinical_plan_from_tool_call(first_call_args)
    else:
        # Model went straight to propose — use the gold label plan
        model_clinical_plan = build_clinical_plan(case)

    # Update state with the resolved plan for the drafter
    state["clinical_plan"] = model_clinical_plan

    # ── Step 3: Draft patches ────────────────────────────────────────────
    t1 = time.monotonic()
    drafted_plan = planner.draft_patch_preview(
        state=state,
        target_document=target_document,
        target_document_content=case.target_document_content,
        supporting_context=list(case.supporting_context),
        requested_tool_name="propose_replace_span",
        requested_tool_instruction=case.user_message,
    )
    drafter_latency = time.monotonic() - t1

    # ── Step 4: Validate ─────────────────────────────────────────────────
    runtime_error = _validate_drafted_plan_against_clinical_plan(
        drafted_plan=drafted_plan,
        clinical_plan=model_clinical_plan,
    )

    patch_sections = sorted(
        {
            str(p.section or "").strip().lower().replace(" ", "_")
            for p in drafted_plan.patches
            if p.section
        }
    )
    expected_sections_set = set(case.affected_sections)
    covered = set(patch_sections) & expected_sections_set
    section_coverage = len(covered) / max(len(expected_sections_set), 1)

    # ── Log outputs and feedback ─────────────────────────────────────────
    t.log_outputs(
        {
            "model_name": model_name,
            "provider_region": provider_region,
            "planner_tool_name": first_call_name,
            "planner_tool_args": first_call_args,
            "planner_tool_call_count": len(raw_tool_calls),
            "planner_content": normalize_message_content(planner_response.content),
            "planner_latency_s": round(planner_latency, 2),
            "drafter_latency_s": round(drafter_latency, 2),
            "total_latency_s": round(planner_latency + drafter_latency, 2),
            "patch_count": len(drafted_plan.patches),
            "patch_sections": patch_sections,
            "model_clinical_plan": model_clinical_plan,
            "runtime_validation_error": runtime_error,
            "failure_stage": "ok" if runtime_error is None else "drafter_validation",
            "drafted_plan": drafted_plan_to_payload(drafted_plan),
        }
    )

    t.log_feedback(
        key="correct_first_tool",
        score=float(
            first_call_name == "set_edit_plan"
            if requires_edit_plan
            else first_call_name == "propose_replace_span"
        ),
    )
    t.log_feedback(
        key="single_tool_call",
        score=float(len(raw_tool_calls) == 1),
    )
    t.log_feedback(
        key="edit_scope_exact_match",
        score=float(
            model_clinical_plan.get("edit_scope") == case.edit_scope
        ),
    )
    t.log_feedback(
        key="impact_level_exact_match",
        score=float(
            model_clinical_plan.get("clinical_impact_level")
            == case.clinical_impact_level
        ),
    )
    t.log_feedback(
        key="section_coverage",
        score=round(section_coverage, 2),
    )
    t.log_feedback(
        key="runtime_valid",
        score=float(runtime_error is None),
    )
    t.log_feedback(
        key="patches_per_expected_section",
        score=round(
            len(drafted_plan.patches) / max(len(case.affected_sections), 1), 2
        ),
    )
    t.log_feedback(
        key="planner_latency_s",
        score=round(planner_latency, 2),
    )
    t.log_feedback(
        key="drafter_latency_s",
        score=round(drafter_latency, 2),
    )

    # ── Hard assertions ──────────────────────────────────────────────────
    assert raw_tool_calls, (
        f"[{provider_id}] Planner returned no tool calls."
    )
    assert len(raw_tool_calls) == 1, (
        f"[{provider_id}] Expected 1 tool call, got {len(raw_tool_calls)}."
    )

    if requires_edit_plan:
        assert first_call_name == "set_edit_plan", (
            f"[{provider_id}] Expected set_edit_plan for {case.edit_scope} "
            f"case, got {first_call_name}."
        )

    assert drafted_plan.patches, (
        f"[{provider_id}] Drafter returned 0 patches for {case.slug}."
    )
    assert runtime_error is None, (
        f"[{provider_id}] Runtime validation failed: {runtime_error}"
    )
