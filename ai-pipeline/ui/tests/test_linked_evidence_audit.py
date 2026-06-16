from __future__ import annotations

from ui.linked_evidence_audit import (
    CONTENT_VIEW_APPLIED,
    CONTENT_VIEW_SOURCE,
    display_generation_content,
    format_cited_evidence_ids_caption,
    has_linked_evidence_audit_data,
    is_legacy_two_step_section,
    planner_raw_output,
    resolve_llm_response_by_step,
)


def test_resolve_llm_response_by_step_prefers_explicit_step() -> None:
    responses = [
        {"step": "planner", "content": "draft"},
        {"step": "renderer", "content": "final"},
    ]
    planner = resolve_llm_response_by_step(responses, step="planner")
    renderer = resolve_llm_response_by_step(responses, step="renderer")
    assert planner is not None and planner["content"] == "draft"
    assert renderer is not None and renderer["content"] == "final"


def test_resolve_llm_response_by_step_falls_back_to_position() -> None:
    responses = [
        {"content": "draft"},
        {"content": "final"},
    ]
    planner = resolve_llm_response_by_step(responses, step="planner")
    renderer = resolve_llm_response_by_step(responses, step="renderer")
    assert planner is not None and planner["content"] == "draft"
    assert renderer is not None and renderer["content"] == "final"


def test_display_generation_content_applied_without_evidence_ids() -> None:
    content = "Cefalea. {{e:t0}}"
    assert (
        display_generation_content(
            content,
            content_view_mode=CONTENT_VIEW_APPLIED,
            show_evidence_ids=False,
        )
        == "Cefalea. "
    )


def test_display_generation_content_applied_with_evidence_ids() -> None:
    content = "Cefalea. {{e:t0}}"
    assert (
        display_generation_content(
            content,
            content_view_mode=CONTENT_VIEW_APPLIED,
            show_evidence_ids=True,
        )
        == content
    )


def test_display_generation_content_source_returns_exact_string() -> None:
    content = "Cefalea. {{e:t0}}"
    assert (
        display_generation_content(
            content,
            content_view_mode=CONTENT_VIEW_SOURCE,
            show_evidence_ids=False,
        )
        == content
    )


def test_display_generation_content_source_ignores_evidence_toggle() -> None:
    content = "Cefalea. {{e:t0}}"
    assert (
        display_generation_content(
            content,
            content_view_mode=CONTENT_VIEW_SOURCE,
            show_evidence_ids=True,
        )
        == content
    )


def test_format_cited_evidence_ids_caption() -> None:
    caption = format_cited_evidence_ids_caption("A {{e:t1,t0}} y B {{e:s2}}")
    assert caption == "IDs citados: s2, t0, t1"


def test_legacy_two_step_without_audit_fields() -> None:
    section_output = {
        "section_id": "motivo_consulta",
        "generation_route": "two_step",
    }
    assert is_legacy_two_step_section(section_output)


def test_planner_raw_output_returns_llm_content_only() -> None:
    section_output = {
        "generation_route": "two_step",
        "planner_items": [{"text": "Cefalea.", "e": ["t0"]}],
        "llm_responses": [
            {"step": "planner", "content": '{"items":[{"text":"Cefalea.","e":["t0"]}]}'},
            {"step": "renderer", "content": "final"},
        ],
    }
    assert (
        planner_raw_output(section_output)
        == '{"items":[{"text":"Cefalea.","e":["t0"]}]}'
    )


def test_legacy_two_step_with_draft_only() -> None:
    section_output = {
        "section_id": "motivo_consulta",
        "generation_route": "two_step",
        "draft_with_evidence": "legacy draft {{e:t0}}",
    }
    assert is_legacy_two_step_section(section_output) is False
    assert has_linked_evidence_audit_data(section_output)
