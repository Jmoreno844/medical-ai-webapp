from __future__ import annotations

from generation.evidence_markers import strip_evidence_markers
from generation.lib import (
    format_section_output_for_detail,
    format_two_step_llm_responses_for_export,
)
from common.llm_response import LlmResponse


def test_strip_evidence_markers_removes_inline_ids() -> None:
    text = "Cefalea de 3 días. {{e:t0,t1}} Sin alarma."
    assert strip_evidence_markers(text) == "Cefalea de 3 días.  Sin alarma."


def test_format_two_step_llm_responses_labels_steps() -> None:
    labeled = format_two_step_llm_responses_for_export(
        [
            LlmResponse(content='{"items":[]}'),
            LlmResponse(content="final {{e:t0}}", usage={"total_tokens": 12}),
        ]
    )
    assert [item["step"] for item in labeled] == ["planner", "renderer"]
    assert labeled[0]["content"] == '{"items":[]}'
    assert labeled[1]["usage"] == {"total_tokens": 12}


def test_compact_section_output_keeps_two_step_audit_fields() -> None:
    section_output = {
        "section_id": "motivo_consulta",
        "generation_route": "two_step",
        "planner_items": [{"text": "Cefalea.", "e": ["t0"]}],
        "planned_items_block": "[1] Cefalea. evidence: t0",
        "llm_responses": [
            {"step": "planner", "content": '{"items":[]}', "usage": {}, "request_params": {}},
            {"step": "renderer", "content": "final", "usage": {}, "request_params": {}},
        ],
        "generation_result": {
            "section_id": "motivo_consulta",
            "content": "Cefalea. {{e:t0}}",
        },
        "raw_response": "should be omitted",
    }
    compact = format_section_output_for_detail(section_output, "compact")
    assert compact["generation_route"] == "two_step"
    assert compact["planner_items"] == [{"text": "Cefalea.", "e": ["t0"]}]
    assert compact["planned_items_block"] == "[1] Cefalea. evidence: t0"
    assert compact["llm_responses"][0]["step"] == "planner"
    assert "raw_response" not in compact


def test_compact_section_output_direct_omits_linked_evidence_fields() -> None:
    section_output = {
        "section_id": "motivo_consulta",
        "generation_route": "direct",
        "generation_result": {
            "section_id": "motivo_consulta",
            "content": "Cefalea.",
        },
        "raw_response": "omitted",
    }
    compact = format_section_output_for_detail(section_output, "compact")
    assert compact["generation_route"] == "direct"
    assert "planner_items" not in compact
    assert "planned_items_block" not in compact
    assert "llm_responses" not in compact
    assert "raw_response" not in compact
