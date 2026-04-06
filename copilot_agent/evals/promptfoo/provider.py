from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def call_api(prompt: str, options: dict, context: dict) -> dict:
    del prompt
    from app.graph.tools import _validate_drafted_plan_against_clinical_plan
    from evals.shared.clinical_cases import (
        build_eval_state,
        build_target_document,
        get_live_clinical_case,
    )
    from evals.shared.live_eval_support import (
        build_promptfoo_planner,
        build_propose_replace_span_tool,
        drafted_plan_to_payload,
        normalize_message_content,
        normalize_tool_calls,
        resolve_promptfoo_provider_config,
    )

    vars_payload = context.get("vars") or {}
    case = get_live_clinical_case(vars_payload["case_slug"])
    mode = vars_payload["mode"]
    provider_config = resolve_promptfoo_provider_config(options=options, context=context)
    planner = build_promptfoo_planner(provider_config)

    try:
        if mode == "planner_tool_call":
            state = build_eval_state(case)
            response = planner.invoke_model(
                state=state,
                messages=state["messages"],
                tools=[build_propose_replace_span_tool()],
            )
            payload = {
                "mode": mode,
                "case_slug": case.slug,
                "provider_id": provider_config["provider_id"],
                "provider_family": provider_config["provider_family"],
                "planner_model": provider_config["planner_model"],
                "tool_call_count": len(response.tool_calls or []),
                "tool_calls": normalize_tool_calls(response.tool_calls),
                "content": normalize_message_content(response.content),
            }
        elif mode == "patch_drafter":
            state = build_eval_state(case)
            drafted_plan = planner.draft_patch_preview(
                state=state,
                target_document=build_target_document(case),
                target_document_content=case.target_document_content,
                supporting_context=list(case.supporting_context),
                requested_tool_name="propose_replace_span",
                requested_tool_instruction=case.user_message,
            )
            payload = {
                "mode": mode,
                "case_slug": case.slug,
                "provider_id": provider_config["provider_id"],
                "provider_family": provider_config["provider_family"],
                "patch_model": provider_config["patch_model"],
                "patch_count": len(drafted_plan.patches),
                "sections": [patch.section for patch in drafted_plan.patches],
                "runtime_validation_error": _validate_drafted_plan_against_clinical_plan(
                    drafted_plan=drafted_plan,
                    clinical_plan=state["clinical_plan"],
                ),
                "drafted_plan": drafted_plan_to_payload(drafted_plan),
            }
        else:
            raise RuntimeError(f"Unsupported promptfoo eval mode: {mode}")
    except Exception as error:
        error_payload = {
            "mode": mode,
            "case_slug": case.slug,
            "provider_id": provider_config["provider_id"],
            "error": str(error),
        }
        return {
            "output": json.dumps(error_payload, ensure_ascii=True, sort_keys=True),
            "error": str(error),
        }

    return {"output": json.dumps(payload, ensure_ascii=True, sort_keys=True)}