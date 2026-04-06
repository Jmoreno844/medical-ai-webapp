from __future__ import annotations

import pytest
from langsmith import testing as t

from app.graph.tools import _validate_drafted_plan_against_clinical_plan
from evals.shared.clinical_cases import (
    all_live_clinical_cases,
    build_eval_state,
    build_target_document,
)
from evals.shared.live_eval_support import drafted_plan_to_payload


@pytest.mark.live_llm
@pytest.mark.langsmith
@pytest.mark.parametrize("case", all_live_clinical_cases(), ids=lambda case: case.slug)
def test_live_drafter_returns_complete_multi_section_patch_plan(
    case,
    live_langchain_planner,
) -> None:
    state = build_eval_state(case)
    target_document = build_target_document(case)

    t.log_inputs(
        {
            "case_slug": case.slug,
            "user_message": case.user_message,
            "clinical_plan": state["clinical_plan"],
            "target_document_id": target_document["document_id"],
            "target_document_excerpt": case.target_document_content[:1200],
        }
    )
    t.log_reference_outputs(
        {
            "expected_sections": list(case.affected_sections),
        }
    )

    drafted_plan = live_langchain_planner.draft_patch_preview(
        state=state,
        target_document=target_document,
        target_document_content=case.target_document_content,
        supporting_context=list(case.supporting_context),
        requested_tool_name="propose_replace_span",
        requested_tool_instruction=case.user_message,
    )
    runtime_validation_error = _validate_drafted_plan_against_clinical_plan(
        drafted_plan=drafted_plan,
        clinical_plan=state["clinical_plan"],
    )
    sections = [str(patch.section or "").strip().lower() for patch in drafted_plan.patches]
    covered_sections = sorted({section for section in sections if section})

    t.log_outputs(
        {
            "patch_count": len(drafted_plan.patches),
            "covered_sections": covered_sections,
            "runtime_validation_error": runtime_validation_error,
            "drafted_plan": drafted_plan_to_payload(drafted_plan),
        }
    )
    t.log_feedback(
        key="runtime_valid",
        score=float(runtime_validation_error is None),
    )
    t.log_feedback(
        key="all_sections_named",
        score=float(all(section for section in sections)),
    )
    t.log_feedback(
        key="expected_sections_covered",
        score=float(set(case.affected_sections).issubset(set(covered_sections))),
    )

    assert drafted_plan.patches, "Drafter should return at least one patch for a multi-section plan."
    assert runtime_validation_error is None