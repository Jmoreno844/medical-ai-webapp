from __future__ import annotations

from ui.app import GENERATION_ROUTE_LABELS, generation_route_labels_for_template
from ui.discovery import list_generation_prompt_versions, template_supports_hybrid
from ui.linked_evidence_audit import (
    has_cluster_planner_audit_data,
    is_cluster_planner_section_output,
)
from ui.runner import StepConfig


def test_generation_route_labels_cover_manual_routes() -> None:
    assert set(GENERATION_ROUTE_LABELS) == {
        "direct",
        "direct_with_evidence",
        "two_step",
        "cluster_planner",
        "hybrid",
    }


def test_generation_route_labels_include_hybrid_for_consulta_template() -> None:
    labels = generation_route_labels_for_template("consulta_estructurada_v001")
    assert "hybrid" in labels
    assert "Híbrido por sección" in labels.values()


def test_generation_route_labels_exclude_hybrid_for_other_templates() -> None:
    labels = generation_route_labels_for_template("minimal_outpatient_v001")
    assert "hybrid" not in labels


def test_template_supports_hybrid_discovery() -> None:
    assert template_supports_hybrid("consulta_estructurada_v001")
    assert not template_supports_hybrid("minimal_outpatient_v001")


def test_step_config_stores_generation_route() -> None:
    config = StepConfig(
        provider="openai",
        model="gpt-5.4-mini",
        prompt_version="v001",
        generation_route="cluster_planner",
    )
    assert config.generation_route == "cluster_planner"
    assert config.linked_evidence_two_step is False


def test_cluster_planner_section_output_detection() -> None:
    section_output = {
        "generation_route": "cluster_planner",
        "cluster_planner_runs": [
            {
                "cluster_id": "case1_a",
                "planner_items": [{"text": "Dolor", "e": ["t0"]}],
                "planned_items_block": "[1] Dolor evidence: t0",
                "raw_response": "{}",
            }
        ],
        "renderer_raw_response": "Paciente con dolor. {{e:t0}}",
        "renderer_skipped": False,
    }
    assert is_cluster_planner_section_output(section_output)
    assert has_cluster_planner_audit_data(section_output)


def test_cluster_planner_section_output_with_renderer_skipped() -> None:
    section_output = {
        "generation_route": "cluster_planner",
        "cluster_planner_runs": [
            {
                "cluster_id": "case1_a",
                "planner_items": [],
                "planned_items_block": "(sin items)",
                "raw_response": '{"items":[]}',
            }
        ],
        "renderer_skipped": True,
    }
    assert is_cluster_planner_section_output(section_output)
    assert has_cluster_planner_audit_data(section_output)
