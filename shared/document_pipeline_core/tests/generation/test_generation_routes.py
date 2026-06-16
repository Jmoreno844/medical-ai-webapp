from __future__ import annotations

import json

import pytest

from document_pipeline_core.classification.lib import ClusterCase
from document_pipeline_core.classification.templates import load_template
from document_pipeline_core.generation.lib import (
    SectionGenerationJob,
    SectionPlanPoint,
    audit_plan_evidence,
    clusters_to_conversation_groups,
    parse_section_plan_result,
    should_use_two_step_generation,
)


def _cluster(case_id: str) -> ClusterCase:
    return ClusterCase(
        id=case_id,
        template_id="minimal_outpatient_v001",
        cluster_json={
            "topic_label": "tema",
            "turns": [
                {"turn_id": 0, "speaker": "MEDICO", "text": "¿Dolor?"},
                {"turn_id": 1, "speaker": "PACIENTE", "text": "Sí, leve."},
            ],
        },
    )


def test_clusters_to_conversation_groups_compact_roles() -> None:
    groups = clusters_to_conversation_groups([_cluster("case1_a")])
    assert groups == [[{"doctor": "¿Dolor?"}, {"patient": "Sí, leve."}]]


def test_clusters_to_conversation_groups_with_turn_ids() -> None:
    groups = clusters_to_conversation_groups(
        [_cluster("case1_a")],
        include_turn_ids=True,
    )
    assert groups[0][0] == {"id": "t0", "doctor": "¿Dolor?"}
    assert groups[0][1] == {"id": "t1", "patient": "Sí, leve."}


def test_should_use_two_step_follows_toggle_only() -> None:
    template = load_template("minimal_outpatient_v001")
    section = next(
        s for s in template.sections if s.section_id == "motivo_consulta"
    )
    job = SectionGenerationJob(
        section_id=section.section_id,
        section=section,
        clusters=[_cluster("case1_a")],
    )
    job_with_spans = SectionGenerationJob(
        section_id=section.section_id,
        section=section,
        clusters=[_cluster("case1_a")],
        evidence_spans=[{"id": "s1", "doc": "lab", "text": "Hb 12"}],
    )
    assert should_use_two_step_generation(job, linked_evidence_two_step=True)
    assert should_use_two_step_generation(job_with_spans, linked_evidence_two_step=True)
    assert not should_use_two_step_generation(job, linked_evidence_two_step=False)
    assert not should_use_two_step_generation(
        job_with_spans,
        linked_evidence_two_step=False,
    )


def test_audit_plan_evidence_rejects_unknown_id() -> None:
    with pytest.raises(ValueError, match="unknown_evidence_id"):
        audit_plan_evidence(
            [SectionPlanPoint(text="dato", evidence=["s99"])],
            allowed_evidence_ids={"s1"},
        )


def test_parse_section_plan_result_validates_evidence() -> None:
    raw = json.dumps(
        {
            "section_id": "motivo_consulta",
            "points": [{"text": "Cefalea.", "evidence": ["t0"]}],
        }
    )
    result = parse_section_plan_result(
        raw,
        expected_section_id="motivo_consulta",
        allowed_evidence_ids={"t0"},
    )
    assert len(result.points) == 1
