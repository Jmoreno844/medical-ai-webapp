from __future__ import annotations

import pytest
from langsmith import testing as t

import app.planner as planner_module
from evals.shared.clinical_cases import all_live_clinical_cases, build_eval_state
from evals.shared.live_eval_support import (
    build_set_edit_plan_tool,
    build_propose_replace_span_tool,
    normalize_message_content,
    normalize_tool_calls,
)


@pytest.mark.live_llm
@pytest.mark.langsmith
@pytest.mark.parametrize("case", all_live_clinical_cases(), ids=lambda case: case.slug)
def test_live_planner_uses_single_schema_safe_tool_call(
    case,
    live_langchain_planner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = build_eval_state(case)
    raw_message_holder: dict[str, object] = {}
    requires_edit_plan = case.edit_scope in {"propagation", "reinterpretation"}
    expected_tool_name = (
        "set_edit_plan" if requires_edit_plan else "propose_replace_span"
    )
    allowed_args = (
        [
            "edit_scope",
            "clinical_impact_level",
            "affected_sections",
            "needs_full_note",
            "needs_external_knowledge",
        ]
        if requires_edit_plan
        else ["instruction", "target_document_id"]
    )

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
            "case_slug": case.slug,
            "user_message": case.user_message,
            "target_document_id": case.target_document_id,
            "affected_sections": list(case.affected_sections),
            "document_excerpt": case.target_document_content[:900],
        }
    )
    t.log_reference_outputs(
        {
            "expected_tool_name": expected_tool_name,
            "expected_target_document_id": case.target_document_id,
            "expected_edit_scope": case.edit_scope,
            "expected_clinical_impact_level": case.clinical_impact_level,
            "expected_affected_sections": list(case.affected_sections),
            "allowed_args": allowed_args,
        }
    )

    eval_tools = (
        [build_set_edit_plan_tool()]
        if requires_edit_plan
        else [build_propose_replace_span_tool()]
    )

    response = live_langchain_planner.invoke_model(
        state=state,
        messages=state["messages"],
        tools=eval_tools,
    )
    raw_message = raw_message_holder.get("message") or response
    raw_tool_calls = normalize_tool_calls(getattr(raw_message, "tool_calls", None))
    first_args = raw_tool_calls[0]["args"] if raw_tool_calls else {}
    instruction = str(first_args.get("instruction") or "").strip()

    t.log_outputs(
        {
            "tool_call_count": len(raw_tool_calls),
            "tool_calls": raw_tool_calls,
            "content": normalize_message_content(response.content),
        }
    )
    t.log_feedback(key="single_tool_call", score=float(len(raw_tool_calls) == 1))
    t.log_feedback(
        key="schema_safe_args",
        score=float(
            all(
                set(tool_call["args"]).issubset(set(allowed_args))
                for tool_call in raw_tool_calls
            )
        ),
    )
    t.log_feedback(
        key="instruction_present",
        score=float(bool(instruction)),
    )

    assert raw_tool_calls, "Planner should call propose_replace_span once the note is already read."
    assert len(raw_tool_calls) == 1
    assert raw_tool_calls[0]["name"] == expected_tool_name
    assert set(first_args).issubset(set(allowed_args))

    if requires_edit_plan:
        affected_sections = {
            str(section).strip().lower().replace(" ", "_")
            for section in first_args.get("affected_sections") or []
        }
        edit_scope = str(first_args.get("edit_scope") or "").strip()
        clinical_impact_level = str(first_args.get("clinical_impact_level") or "").strip()

        t.log_feedback(
            key="edit_scope_exact_match",
            score=float(edit_scope == case.edit_scope),
        )
        t.log_feedback(
            key="impact_level_exact_match",
            score=float(clinical_impact_level == case.clinical_impact_level),
        )

        assert edit_scope in {"propagation", "reinterpretation"}
        assert clinical_impact_level in {"factual", "clinical"}
        assert first_args.get("needs_full_note") is True
        assert set(case.affected_sections).issubset(affected_sections)
    else:
        assert first_args.get("target_document_id") == case.target_document_id
        assert instruction