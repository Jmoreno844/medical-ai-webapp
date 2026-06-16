from __future__ import annotations

import pytest

from classification.lib import ClusterCase
from classification.templates import load_template
from common.llm_response import LlmResponse
from generation.generate import run_two_step_section_generation
from generation.lib import GenerationValidationError, SectionGenerationJob


def _cluster(case_id: str = "case1_a") -> ClusterCase:
    return ClusterCase(
        id=case_id,
        template_id="minimal_outpatient_v001",
        cluster_json={
            "topic_label": "tema",
            "turns": [
                {"turn_id": 0, "speaker": "PACIENTE", "text": "Dolor de cabeza."},
            ],
        },
    )


def _motivo_job() -> SectionGenerationJob:
    template = load_template("minimal_outpatient_v001")
    section = next(
        item for item in template.sections if item.section_id == "motivo_consulta"
    )
    return SectionGenerationJob(
        section_id=section.section_id,
        section=section,
        clusters=[_cluster()],
    )


def test_planner_failure_includes_section_and_substep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import generation.generate as generate_module

    def fake_llm(**_kwargs: object) -> LlmResponse:
        return LlmResponse(
            content='{"items":[{"text":"Cefalea.","e":["unknown_evidence"]}]}'
        )

    monkeypatch.setattr(generate_module, "call_generation_llm_detailed", fake_llm)
    job = _motivo_job()
    template = load_template("minimal_outpatient_v001")

    with pytest.raises(GenerationValidationError) as exc_info:
        run_two_step_section_generation(
            job=job,
            template=template,
            model_spec=type("Spec", (), {"provider": "openai", "model": "x"})(),  # type: ignore[arg-type]
            prompt_version="v001",
        )

    exc = exc_info.value
    assert exc.section_id == "motivo_consulta"
    assert exc.generation_substep == "planner"
    diagnostics = exc.diagnostics()
    assert diagnostics["generation_route"] == "two_step"
    assert diagnostics["allowed_evidence_ids"] == ["t0"]
    assert diagnostics["evidence_count"] == 0


def test_renderer_failure_preserves_planner_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import generation.generate as generate_module

    call_count = 0

    def fake_llm(**kwargs: object) -> LlmResponse:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return LlmResponse(content='{"items":[{"text":"Cefalea.","e":["t0"]}]}')
        return LlmResponse(content="Cefalea. {{e:bad_id}}")

    monkeypatch.setattr(generate_module, "call_generation_llm_detailed", fake_llm)
    job = _motivo_job()
    template = load_template("minimal_outpatient_v001")

    with pytest.raises(GenerationValidationError) as exc_info:
        run_two_step_section_generation(
            job=job,
            template=template,
            model_spec=type("Spec", (), {"provider": "openai", "model": "x"})(),  # type: ignore[arg-type]
            prompt_version="v001",
        )

    exc = exc_info.value
    assert exc.generation_substep == "renderer"
    diagnostics = exc.diagnostics()
    assert diagnostics["planner_items"] == [{"text": "Cefalea.", "e": ["t0"]}]
    assert diagnostics["planned_items_block"] == "[1] Cefalea. evidence: t0"
    assert diagnostics["planner_response"] == (
        '{"items":[{"text":"Cefalea.","e":["t0"]}]}'
    )


def test_two_step_generation_demotes_renderer_internal_headings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import generation.generate as generate_module

    call_count = 0

    def fake_llm(**kwargs: object) -> LlmResponse:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return LlmResponse(content='{"items":[{"text":"Cefalea.","e":["t0"]}]}')
        return LlmResponse(content="### Neurológico\nCefalea. {{e:t0}}")

    monkeypatch.setattr(generate_module, "call_generation_llm_detailed", fake_llm)
    job = _motivo_job()
    template = load_template("minimal_outpatient_v001")

    result, *_ = run_two_step_section_generation(
        job=job,
        template=template,
        model_spec=type("Spec", (), {"provider": "openai", "model": "x"})(),  # type: ignore[arg-type]
        prompt_version="v001",
    )

    assert result.content == "Neurológico: Cefalea. {{e:t0}}"
