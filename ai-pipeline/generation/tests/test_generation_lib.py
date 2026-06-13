from __future__ import annotations

import json

import pytest

from classification.lib import ClusterCase
from classification.templates import load_template
from common.context_claims import (
    ClaimAssignment,
    ClaimSourceType,
    ClaimType,
    ClinicalClaim,
)
from generation.lib import (
    ClusterAssignmentInput,
    enrich_generation_session_result_for_export,
    format_generation_output_for_detail,
    group_clusters_by_section,
    load_classification_assignments,
    parse_section_generation_result,
    plan_section_generation,
    render_section_user_payload,
    template_id_from_classification_result,
)


def _cluster(case_id: str) -> ClusterCase:
    return ClusterCase(
        id=case_id,
        template_id="minimal_outpatient_v001",
        cluster_json={
            "topic_label": case_id.removeprefix("case1_"),
            "turns": [
                {"turn_id": 0, "speaker": "PACIENTE", "text": f"tema {case_id}"},
            ],
        },
    )


def test_plan_section_generation_includes_claim_only_section() -> None:
    template = load_template("minimal_outpatient_v001")
    clusters_by_id = {"case1_a": _cluster("case1_a")}
    assignments = [
        ClusterAssignmentInput(cluster_id="case1_a", section_ids=["motivo_consulta"])
    ]
    claim = ClinicalClaim(
        claim_id="dn_01",
        text="TA 138/88 al llegar.",
        source_type=ClaimSourceType.DOCTOR_NOTE,
        claim_type=ClaimType.MEASUREMENT,
    )
    plan = plan_section_generation(
        assignments,
        clusters_by_id,
        template,
        claim_assignments=[
            ClaimAssignment(
                claim_id="dn_01",
                section_ids=["examen_fisico"],
            )
        ],
        claims_by_id={"dn_01": claim},
    )
    section_ids = {job.section_id for job in plan.jobs}
    assert "motivo_consulta" in section_ids
    assert "examen_fisico" in section_ids
    examen_job = next(job for job in plan.jobs if job.section_id == "examen_fisico")
    assert examen_job.clusters == []
    assert examen_job.enrichment_claims == [claim]


def test_render_section_user_payload_includes_enrichment_claims() -> None:
    template = load_template("minimal_outpatient_v001")
    section = next(
        section for section in template.sections if section.section_id == "examen_fisico"
    )
    claim = ClinicalClaim(
        claim_id="dn_01",
        text="Paciente pálido.",
        source_type=ClaimSourceType.DOCTOR_NOTE,
        claim_type=ClaimType.OBSERVATION,
    )
    payload = json.loads(
        render_section_user_payload(
            section=section,
            clusters=[],
            enrichment_claims=[claim],
            template=template,
        )
    )
    assert payload["clusters"] == []
    assert payload["enrichment_claims"][0]["claim_id"] == "dn_01"


def test_group_clusters_by_section_supports_multi_section_cluster() -> None:
    template = load_template("minimal_outpatient_v001")
    clusters_by_id = {
        "case1_a": _cluster("case1_a"),
        "case1_b": _cluster("case1_b"),
    }
    assignments = [
        ClusterAssignmentInput(
            cluster_id="case1_a",
            section_ids=["motivo_consulta", "enfermedad_actual"],
        ),
        ClusterAssignmentInput(cluster_id="case1_b", section_ids=["antecedentes"]),
    ]
    grouped = group_clusters_by_section(assignments, clusters_by_id, template)
    assert [cluster.id for cluster in grouped["motivo_consulta"]] == ["case1_a"]
    assert [cluster.id for cluster in grouped["enfermedad_actual"]] == ["case1_a"]
    assert [cluster.id for cluster in grouped["antecedentes"]] == ["case1_b"]
    assert grouped["examen_fisico"] == []


def test_plan_section_generation_skips_empty_sections() -> None:
    template = load_template("minimal_outpatient_v001")
    clusters_by_id = {"case1_a": _cluster("case1_a")}
    assignments = [
        ClusterAssignmentInput(cluster_id="case1_a", section_ids=["motivo_consulta"])
    ]
    plan = plan_section_generation(assignments, clusters_by_id, template)
    assert plan.job_count == 1
    assert plan.jobs[0].section_id == "motivo_consulta"
    skipped_ids = {item["section_id"] for item in plan.skipped_sections}
    assert "examen_fisico" in skipped_ids
    assert "enfermedad_actual" in skipped_ids


def test_parse_section_generation_result_rejects_section_id_mismatch() -> None:
    raw = json.dumps({"section_id": "otra", "content": "texto"})
    with pytest.raises(ValueError, match="section_id_mismatch"):
        parse_section_generation_result(raw, expected_section_id="motivo_consulta")


def test_load_classification_assignments_from_result_shape(tmp_path) -> None:
    result_path = tmp_path / "classification.json"
    result_path.write_text(
        json.dumps(
            {
                "template_id": "minimal_outpatient_v001",
                "classification_session_result": {
                    "assignments": [
                        {
                            "cluster_id": "case1_a",
                            "section_ids": ["motivo_consulta"],
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    assignments = load_classification_assignments(result_path)
    assert len(assignments) == 1
    assert assignments[0].cluster_id == "case1_a"
    assert (
        template_id_from_classification_result(result_path)
        == "minimal_outpatient_v001"
    )


def test_enrich_generation_session_result_for_export() -> None:
    from generation.lib import GenerationSessionResult, SectionGenerationResult

    template = load_template("minimal_outpatient_v001")
    session = GenerationSessionResult(
        sections=[
            SectionGenerationResult(
                section_id="motivo_consulta",
                content="Cansancio al subir escaleras.",
            )
        ],
        skipped_sections=[
            {"section_id": "examen_fisico", "heading": "Examen físico"},
        ],
    )
    exported = enrich_generation_session_result_for_export(
        session,
        template,
        cluster_ids_by_section={"motivo_consulta": ["case1_a"]},
    )
    assert exported["section_count"] == 1
    assert exported["sections"][0]["heading"] == "Motivo de consulta"
    assert exported["skipped_section_count"] == 1


def test_compact_output_detail_omits_raw_response() -> None:
    payload = {
        "provider": "openai",
        "generation_result": {
            "section_id": "motivo_consulta",
            "content": "texto",
        },
        "raw_response": '{"section_id":"motivo_consulta","content":"texto"}',
    }
    compact = format_generation_output_for_detail(payload, "compact")
    assert "raw_response" not in compact


def test_format_section_output_for_detail_keeps_thinking_text() -> None:
    from generation.lib import format_section_output_for_detail

    section_output = {
        "section_id": "motivo_consulta",
        "thinking": "razonamiento de prueba",
        "thinking_source": "message.reasoning",
        "llm_usage": {
            "completion_tokens_details": {"reasoning_tokens": 42},
        },
        "raw_response": "ignored in compact",
    }
    compact = format_section_output_for_detail(section_output, "compact")
    assert compact["thinking"] == "razonamiento de prueba"
    assert compact["thinking_chars"] == len("razonamiento de prueba")
    assert compact["thinking_source"] == "message.reasoning"
    assert "raw_response" not in compact
