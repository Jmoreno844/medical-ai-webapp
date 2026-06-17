from __future__ import annotations

import pytest

from app.pipeline.config import PipelineConfig
from app.pipeline.generation_route import resolve_effective_generation_route
from app.pipeline.orchestrator import run_document_pipeline
from document_pipeline_core.classification.templates import load_template
from document_pipeline_core.common.context_inputs import ContextInputs
from document_pipeline_core.common.templates import ClinicalTemplate
from document_pipeline_core.generation.lib import (
    GENERATION_ROUTE_CLUSTER_PLANNER,
    GENERATION_ROUTE_DIRECT_WITH_EVIDENCE,
    GENERATION_ROUTE_HYBRID,
)
from document_pipeline_core.orchestrators.document_pipeline import (
    DocumentPipelineRunResult,
    DocumentPipelineStepResult,
)


def _minimal_transcript() -> dict[str, object]:
    return {
        "session_id": "sess1",
        "chunks": [
            {
                "chunk_id": "s0",
                "turns": [
                    {"turn_id": 0, "speaker": "PACIENTE", "text": "Dolor."},
                ],
            }
        ],
    }


def test_hybrid_template_uses_effective_route_hybrid() -> None:
    template = load_template("consulta_estructurada_v001")
    config = PipelineConfig(generation_route="direct")

    resolved = resolve_effective_generation_route(
        template=template,
        pipeline_config=config,
    )

    assert resolved.template_supports_hybrid is True
    assert resolved.requested_generation_route == "direct"
    assert resolved.effective_generation_route == GENERATION_ROUTE_HYBRID


def test_non_hybrid_template_keeps_config_route() -> None:
    template = ClinicalTemplate.model_validate(
        {
            "id": "minimal_test_v001",
            "name": "Minimal",
            "document_kind": "document",
            "sections": [
                {
                    "section_id": "motivo",
                    "heading": "Motivo",
                    "description": "",
                    "generation": {
                        "guidelines": "",
                        "mode": "narrative",
                        "preferred_route": "direct_with_evidence",
                    },
                },
            ],
        }
    )
    config = PipelineConfig(generation_route="two_step")

    resolved = resolve_effective_generation_route(
        template=template,
        pipeline_config=config,
    )

    assert resolved.template_supports_hybrid is False
    assert resolved.requested_generation_route == "two_step"
    assert resolved.effective_generation_route == "two_step"


def test_consulta_estructurada_section_preferred_routes() -> None:
    template = load_template("consulta_estructurada_v001")
    estudios = template.section_by_id("estudios_y_resultados")
    analisis = template.section_by_id("analisis_y_plan")
    assert estudios is not None
    assert analisis is not None
    assert estudios.generation.preferred_route == GENERATION_ROUTE_DIRECT_WITH_EVIDENCE
    assert analisis.generation.preferred_route == GENERATION_ROUTE_CLUSTER_PLANNER


def test_orchestrator_passes_hybrid_route_for_consulta_estructurada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run_document_pipeline_v2(**kwargs: object) -> DocumentPipelineRunResult:
        captured.update(kwargs)
        return DocumentPipelineRunResult(
            document_markdown="",
            step_results=[],
        )

    monkeypatch.setattr(
        "app.pipeline.orchestrator.run_document_pipeline_v2",
        fake_run_document_pipeline_v2,
    )

    template = load_template("consulta_estructurada_v001")
    config = PipelineConfig(generation_route="direct")

    run_document_pipeline(
        session_id="sess1",
        template=template,
        transcript_json=_minimal_transcript(),
        context_inputs=ContextInputs(),
        pipeline_config=config,
    )

    assert captured["generation_route"] == GENERATION_ROUTE_HYBRID


def test_orchestrator_enriches_generation_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_document_pipeline_v2(**_kwargs: object) -> DocumentPipelineRunResult:
        return DocumentPipelineRunResult(
            document_markdown="",
            step_results=[
                DocumentPipelineStepResult(
                    step="generation",
                    duration_ms=10,
                    metadata={
                        "route": GENERATION_ROUTE_HYBRID,
                        "section_routes": {
                            "estudios_y_resultados": GENERATION_ROUTE_DIRECT_WITH_EVIDENCE,
                            "analisis_y_plan": GENERATION_ROUTE_CLUSTER_PLANNER,
                        },
                    },
                ),
            ],
        )

    monkeypatch.setattr(
        "app.pipeline.orchestrator.run_document_pipeline_v2",
        fake_run_document_pipeline_v2,
    )

    template = load_template("consulta_estructurada_v001")
    config = PipelineConfig(generation_route="direct")

    result = run_document_pipeline(
        session_id="sess1",
        template=template,
        transcript_json=_minimal_transcript(),
        context_inputs=ContextInputs(),
        pipeline_config=config,
    )

    generation_meta = result.step_results[0].metadata
    assert generation_meta["requested_generation_route"] == "direct"
    assert generation_meta["effective_generation_route"] == GENERATION_ROUTE_HYBRID
    assert generation_meta["template_supports_hybrid"] is True
    assert (
        generation_meta["section_routes"]["estudios_y_resultados"]
        == GENERATION_ROUTE_DIRECT_WITH_EVIDENCE
    )
    assert (
        generation_meta["section_routes"]["analisis_y_plan"]
        == GENERATION_ROUTE_CLUSTER_PLANNER
    )


def test_hybrid_route_ignores_pipeline_direct_env_for_supported_template() -> None:
    template = load_template("consulta_estructurada_v001")
    for env_route in ("direct", "two_step", "cluster_planner"):
        config = PipelineConfig(generation_route=env_route)
        resolved = resolve_effective_generation_route(
            template=template,
            pipeline_config=config,
        )
        assert resolved.effective_generation_route == GENERATION_ROUTE_HYBRID
