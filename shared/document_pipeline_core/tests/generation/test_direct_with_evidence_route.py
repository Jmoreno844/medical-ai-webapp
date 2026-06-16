from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from document_pipeline_core.classification.lib import ClusterCase
from document_pipeline_core.classification.templates import load_template
from document_pipeline_core.common.llm_response import LlmResponse
from document_pipeline_core.common.providers import ModelSpec
from document_pipeline_core.generation.evidence_markers import CONTEXT_BRIEF_EVIDENCE_ID
from document_pipeline_core.generation.generate import run_section_generation
from document_pipeline_core.generation.lib import (
    GENERATION_ROUTE_DIRECT_WITH_EVIDENCE,
    GenerationValidationError,
    SectionGenerationJob,
    collect_allowed_evidence_id_set,
    generation_prompt_files_for_route,
    render_direct_with_evidence_payload,
    resolve_generation_route,
)


def _cluster(case_id: str, *, turn_id: int = 0) -> ClusterCase:
    return ClusterCase(
        id=case_id,
        template_id="minimal_outpatient_v001",
        cluster_json={
            "topic_label": f"Tema {case_id}",
            "turns": [
                {"turn_id": turn_id, "speaker": "MEDICO", "text": "¿Dolor?"},
                {"turn_id": turn_id + 1, "speaker": "PACIENTE", "text": "Sí."},
            ],
        },
    )


def _section_job(
    *,
    clusters: list[ClusterCase] | None = None,
    context: str = "",
) -> SectionGenerationJob:
    template = load_template("minimal_outpatient_v001")
    section = next(s for s in template.sections if s.section_id == "motivo_consulta")
    resolved_clusters = [_cluster("case1_a")] if clusters is None else clusters
    return SectionGenerationJob(
        section_id=section.section_id,
        section=section,
        clusters=resolved_clusters,
        context=context,
    )


def _llm_response(content: str) -> LlmResponse:
    return LlmResponse(
        content=content,
        thinking=None,
        thinking_source=None,
        usage={"input_tokens": 1, "output_tokens": 1},
        request_params={},
        timing=None,
    )


def test_resolve_generation_route_accepts_direct_with_evidence() -> None:
    assert (
        resolve_generation_route(generation_route="direct_with_evidence")
        == GENERATION_ROUTE_DIRECT_WITH_EVIDENCE
    )


def test_generation_prompt_files_for_direct_with_evidence() -> None:
    files = generation_prompt_files_for_route(
        GENERATION_ROUTE_DIRECT_WITH_EVIDENCE,
        "v001",
    )
    assert "direct_with_evidence" in files
    assert files["direct_with_evidence"].endswith(
        "generation_direct_with_evidence_prompt_v001.py"
    )


def test_generation_prompt_files_for_cluster_planner_after_move() -> None:
    files = generation_prompt_files_for_route("cluster_planner", "v001")
    assert files["cluster_planner"].endswith("cluster_planner_route/cluster_planner_prompt_v001.py")
    assert files["cluster_renderer"].endswith(
        "cluster_planner_route/cluster_renderer_prompt_v001.py"
    )


def test_direct_with_evidence_payload_includes_turn_ids_and_context_c1() -> None:
    job = _section_job(context="Epicrisis previa: anemia.")
    template = load_template("minimal_outpatient_v001")
    payload = render_direct_with_evidence_payload(
        job,
        template,
        prompt_version="v001",
    )
    assert '"id": "t0"' in payload
    assert "context_brief" in payload
    assert "Epicrisis previa: anemia." in payload
    allowed = collect_allowed_evidence_id_set(job)
    assert CONTEXT_BRIEF_EVIDENCE_ID in allowed


def test_direct_with_evidence_rejects_unknown_evidence_ids() -> None:
    job = _section_job()
    template = load_template("minimal_outpatient_v001")
    model_spec = ModelSpec(alias="openai", provider="openai", model="gpt-5.4-mini")
    invalid_payload = json.dumps(
        {
            "section_id": "motivo_consulta",
            "content": "Dolor leve. {{e:t999}}",
        },
        ensure_ascii=False,
    )

    with patch(
        "document_pipeline_core.generation.generate.call_generation_llm_detailed",
        return_value=_llm_response(invalid_payload),
    ):
        with pytest.raises(GenerationValidationError):
            run_section_generation(
                job=job,
                template=template,
                model_spec=model_spec,
                system_prompt="ignored",
                prompt_version="v001",
                generation_route=GENERATION_ROUTE_DIRECT_WITH_EVIDENCE,
            )


def test_direct_with_evidence_accepts_valid_markers() -> None:
    job = _section_job()
    template = load_template("minimal_outpatient_v001")
    model_spec = ModelSpec(alias="openai", provider="openai", model="gpt-5.4-mini")
    valid_payload = json.dumps(
        {
            "section_id": "motivo_consulta",
            "content": "Paciente refiere dolor. {{e:t0}}",
        },
        ensure_ascii=False,
    )

    with patch(
        "document_pipeline_core.generation.generate.call_generation_llm_detailed",
        return_value=_llm_response(valid_payload),
    ):
        (
            result,
            responses,
            _ms,
            route,
            *_rest,
        ) = run_section_generation(
            job=job,
            template=template,
            model_spec=model_spec,
            system_prompt="ignored",
            prompt_version="v001",
            generation_route=GENERATION_ROUTE_DIRECT_WITH_EVIDENCE,
        )

    assert route == GENERATION_ROUTE_DIRECT_WITH_EVIDENCE
    assert len(responses) == 1
    assert "{{e:t0}}" in result.content
