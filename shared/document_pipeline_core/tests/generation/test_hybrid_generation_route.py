from __future__ import annotations

import json
from unittest.mock import patch

from document_pipeline_core.classification.lib import ClusterCase
from document_pipeline_core.classification.templates import load_template
from document_pipeline_core.common.llm_response import LlmResponse
from document_pipeline_core.common.providers import ModelSpec
from document_pipeline_core.common.templates import template_supports_hybrid_generation
from document_pipeline_core.generation.generate import run_generation_session
from document_pipeline_core.generation.lib import (
    GENERATION_ROUTE_CLUSTER_PLANNER,
    GENERATION_ROUTE_DIRECT_WITH_EVIDENCE,
    GENERATION_ROUTE_HYBRID,
    ClusterAssignmentInput,
    resolve_generation_route,
    resolve_section_generation_route,
)


def _cluster(case_id: str, *, turn_id: int = 0) -> ClusterCase:
    return ClusterCase(
        id=case_id,
        template_id="consulta_estructurada_v001",
        cluster_json={
            "topic_label": f"Tema {case_id}",
            "turns": [
                {"turn_id": turn_id, "speaker": "MEDICO", "text": "¿Dolor?"},
                {"turn_id": turn_id + 1, "speaker": "PACIENTE", "text": "Sí."},
            ],
        },
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


def test_resolve_generation_route_accepts_hybrid() -> None:
    assert resolve_generation_route(generation_route="hybrid") == GENERATION_ROUTE_HYBRID


def test_consulta_estructurada_template_supports_hybrid() -> None:
    template = load_template("consulta_estructurada_v001")
    assert template_supports_hybrid_generation(template)
    motivo = next(s for s in template.sections if s.section_id == "motivo_consulta")
    enfermedad = next(s for s in template.sections if s.section_id == "enfermedad_actual")
    assert (
        resolve_section_generation_route(
            requested_route=GENERATION_ROUTE_HYBRID,
            section=motivo,
        )
        == GENERATION_ROUTE_DIRECT_WITH_EVIDENCE
    )
    assert (
        resolve_section_generation_route(
            requested_route=GENERATION_ROUTE_HYBRID,
            section=enfermedad,
        )
        == GENERATION_ROUTE_CLUSTER_PLANNER
    )


def test_hybrid_persists_real_route_per_section() -> None:
    template = load_template("consulta_estructurada_v001")
    clusters = [_cluster("case1_a")]
    assignments = [
        ClusterAssignmentInput(
            cluster_id="case1_a",
            section_ids=["motivo_consulta", "enfermedad_actual"],
        ),
    ]
    model_spec = ModelSpec(alias="openai", provider="openai", model="gpt-5.4-mini")
    call_index = 0

    def fake_call(**kwargs: object) -> LlmResponse:
        nonlocal call_index
        call_index += 1
        schema = kwargs.get("output_schema")
        properties = (
            schema.get("properties", {})
            if isinstance(schema, dict)
            else {}
        )
        if "items" in properties:
            return _llm_response(
                json.dumps({"items": [{"text": "Dato.", "e": ["t0"]}]}, ensure_ascii=False)
            )
        if "section_id" in properties:
            return _llm_response(
                json.dumps(
                    {
                        "section_id": "motivo_consulta",
                        "content": "Dolor. {{e:t0}}",
                    },
                    ensure_ascii=False,
                )
            )
        return _llm_response("Evolución con dolor. {{e:t0}}")

    with patch(
        "document_pipeline_core.generation.generate.call_generation_llm_detailed",
        side_effect=fake_call,
    ):
        session_run = run_generation_session(
            session_id="sess1",
            assignments=assignments,
            clusters=clusters,
            template=template,
            model_spec=model_spec,
            system_prompt="ignored",
            prompt_version="v001",
            generation_route=GENERATION_ROUTE_HYBRID,
            cluster_planner_concurrency=1,
        )

    routes_by_section = {
        section_run.section_id: section_run.generation_route
        for section_run in session_run.section_runs
    }
    assert routes_by_section["motivo_consulta"] == GENERATION_ROUTE_DIRECT_WITH_EVIDENCE
    assert routes_by_section["enfermedad_actual"] == GENERATION_ROUTE_CLUSTER_PLANNER
