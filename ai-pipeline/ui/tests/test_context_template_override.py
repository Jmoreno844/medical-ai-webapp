from __future__ import annotations

from pathlib import Path

import pytest

from common.case_paths import CONTEXT_CASES_INDEX
from context_pipeline.config import (
    ContextPipelineConfig,
    build_context_pipeline_prompt_bundle,
)
from common.context_spans import ClassifyClustersResult, TriageResult
from common.templates import DEFAULT_TEMPLATES_DIR, load_template
from context_pipeline.session import ContextPipelineRun, run_context_pipeline_session


def _minimal_context_run(template_id: str) -> ContextPipelineRun:
    return ContextPipelineRun(
        session_id="case1",
        template_id=template_id,
        encounter_date="2026-06-14",
        doctor_items=[],
        is_pasted=False,
        triage_result=TriageResult(),
        directives=[],
        approved_note_spans=[],
        document_spans=[],
        span_pool=[],
        filtered_spans=[],
        clusters=[],
        classify_result=ClassifyClustersResult(),
        adapter_jobs={},
        section_context={
            section.section_id: f"brief for {section.section_id}"
            for section in load_template(
                template_id, templates_dir=DEFAULT_TEMPLATES_DIR
            ).sections
        },
        section_evidence={},
        llm_calls=[],
    )


def test_run_context_pipeline_session_uses_template_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_core(**kwargs: object) -> ContextPipelineRun:
        prompt_bundle = kwargs["prompt_bundle"]
        captured["template_id"] = kwargs["template_id"]
        captured["section_ids"] = [
            section.section_id for section in kwargs["template"].sections
        ]
        captured["prompt_versions"] = prompt_bundle.versions_by_step()
        return _minimal_context_run(str(kwargs["template_id"]))

    monkeypatch.setattr(
        "context_pipeline.session._run_context_pipeline_core",
        fake_core,
    )

    run_context_pipeline_session(
        case_id="case1",
        cases_index=CONTEXT_CASES_INDEX,
        templates_dir=DEFAULT_TEMPLATES_DIR,
        model_spec=type("Spec", (), {"provider": "openai", "model": "x"})(),  # type: ignore[arg-type]
        prompt_bundle=build_context_pipeline_prompt_bundle(
            ContextPipelineConfig.with_defaults()
        ),
        include_doctor_note=False,
        include_documents=False,
        template_id_override="consulta_estructurada_v001",
    )

    assert captured["template_id"] == "consulta_estructurada_v001"
    assert "identificacion" in captured["section_ids"]
    assert "analisis_y_plan" in captured["section_ids"]


def test_run_context_pipeline_step_exports_override_template_sections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ui.context_runner import run_context_pipeline_step
    from ui.runner import StepConfig

    override_template = "consulta_estructurada_v001"
    context_run = _minimal_context_run(override_template)

    monkeypatch.setattr(
        "ui.context_runner.run_context_pipeline_session",
        lambda **kwargs: context_run,
    )
    def _fake_persist(path: Path, record: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr("ui.runner._persist_results", _fake_persist)
    monkeypatch.setattr(
        "ui.context_runner.AI_PIPELINE_ROOT",
        tmp_path,
    )

    config = StepConfig(
        provider="openai",
        model="gpt",
        prompt_version="v001",
        openai_reasoning_effort=None,
        linked_evidence_two_step=False,
    )
    output = run_context_pipeline_step(
        context_case_id="case1",
        config=config,
        include_doctor_note=False,
        include_documents=False,
        template_id_override=override_template,
    )

    section_context = output.result_record.get("section_context")
    assert isinstance(section_context, dict)
    assert "identificacion" in section_context
    assert "enfermedad_actual" in section_context
    assert output.result_record.get("template_id") == override_template
    assert output.result_record.get("template_id_override") == override_template
