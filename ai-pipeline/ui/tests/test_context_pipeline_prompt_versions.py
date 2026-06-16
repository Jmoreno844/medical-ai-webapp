from __future__ import annotations

from ui.context_runner import _default_context_prompt_bundle, run_context_ad_hoc_pipeline_step
from ui.runner import StepConfig


def test_default_context_prompt_bundle_uses_per_substep_versions() -> None:
    bundle = _default_context_prompt_bundle()
    versions = bundle.versions_by_step()
    assert versions["context_triage"] == "v001"
    assert versions["context_filter_spans"] == "v002"
    assert versions["context_classify_clusters"] == "v002"
    assert versions["context_section_adapter"] == "v003"
    assert versions["context_document_directive_filter"] == "v001"


def test_build_context_pipeline_prompt_bundle_resolves_prompts() -> None:
    from context_pipeline.config import (
        ContextPipelineConfig,
        build_context_pipeline_prompt_bundle,
    )

    bundle = build_context_pipeline_prompt_bundle(ContextPipelineConfig.with_defaults())
    assert bundle.triage.system_prompt.strip()
    assert bundle.filter_spans.system_prompt.strip()
    assert bundle.triage.prompt_reference.endswith(".py")


def test_run_context_ad_hoc_pipeline_step_exports_prompt_versions(
    tmp_path,
    monkeypatch,
) -> None:
    from context_pipeline.session import ContextPipelineRun
    from common.context_spans import ClassifyClustersResult, TriageResult

    bundle = _default_context_prompt_bundle()

    def _fake_ad_hoc(**kwargs: object) -> ContextPipelineRun:
        assert kwargs["prompt_bundle"].versions_by_step() == bundle.versions_by_step()
        return ContextPipelineRun(
            session_id="adhoc",
            template_id="consulta_estructurada_v001",
            encounter_date=None,
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
            section_context={},
            section_evidence={},
            llm_calls=[],
        )

    def _fake_persist(path, record: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr("ui.context_runner.run_context_pipeline_ad_hoc", _fake_ad_hoc)
    monkeypatch.setattr("ui.runner._persist_results", _fake_persist)
    monkeypatch.setattr("ui.context_runner.AI_PIPELINE_ROOT", tmp_path)

    from contextlib import contextmanager

    @contextmanager
    def _noop_env(_config: object):
        yield

    monkeypatch.setattr("ui.runner.apply_step_config_env", _noop_env)

    config = StepConfig(
        provider="openai",
        model="gpt",
        prompt_version="v999",
        openai_reasoning_effort=None,
        linked_evidence_two_step=False,
    )
    output = run_context_ad_hoc_pipeline_step(
            session_id="adhoc",
            template_id="consulta_estructurada_v001",
            config=config,
            doctor_note="Nota breve del médico.",
    )

    prompt_versions = output.result_record.get("prompt_versions")
    assert isinstance(prompt_versions, dict)
    assert prompt_versions["context_triage"] == "v001"
    assert prompt_versions["context_filter_spans"] == "v002"
    assert prompt_versions["context_section_adapter"] == "v003"
