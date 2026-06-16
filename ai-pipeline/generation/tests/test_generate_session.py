from __future__ import annotations

import threading
import time

import pytest

from classification.lib import ClusterCase
from classification.templates import load_template
from common.llm_response import LlmResponse
from generation.generate import (
    SectionGenerationRun,
    run_generation_session,
)
from generation.lib import (
    ClusterAssignmentInput,
    SectionGenerationJob,
    SectionGenerationResult,
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


def test_run_generation_session_runs_sections_in_parallel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template = load_template("minimal_outpatient_v001")
    clusters = [_cluster("case1_a"), _cluster("case1_b")]
    assignments = [
        ClusterAssignmentInput(cluster_id="case1_a", section_ids=["motivo_consulta"]),
        ClusterAssignmentInput(cluster_id="case1_b", section_ids=["antecedentes"]),
    ]
    active_calls = 0
    max_active_calls = 0
    lock = threading.Lock()
    sleep_seconds = 0.2

    def fake_job(
        job: SectionGenerationJob,
        **kwargs: object,
    ) -> SectionGenerationRun:
        nonlocal active_calls, max_active_calls
        with lock:
            active_calls += 1
            max_active_calls = max(max_active_calls, active_calls)
        time.sleep(sleep_seconds)
        with lock:
            active_calls -= 1
        return SectionGenerationRun(
            section_id=job.section_id,
            cluster_ids=job.cluster_ids,
            context_present=job.context_present,
            context_chars=job.context_chars,
            result=SectionGenerationResult(
                section_id=job.section_id,
                content=f"contenido {job.section_id}",
            ),
            llm_responses=[LlmResponse(content="{}")],
            raw_response="{}",
            response_time_ms=200,
        )

    import generation.generate as generate_module

    monkeypatch.setattr(generate_module, "_run_section_generation_job", fake_job)

    session_run = run_generation_session(
        session_id="case1",
        assignments=assignments,
        clusters=clusters,
        template=template,
        model_spec=type("Spec", (), {"provider": "openai", "model": "x"})(),  # type: ignore[arg-type]
        system_prompt="test",
        section_concurrency=0,
    )

    assert session_run.section_execution_mode == "parallel"
    assert max_active_calls == 2
    assert session_run.total_response_time_ms < int(sleep_seconds * 2000)
    assert session_run.sum_section_response_time_ms >= int(sleep_seconds * 2000)
    assert len(session_run.session_result.skipped_sections) == 4


def test_run_generation_session_skips_sections_without_clusters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template = load_template("minimal_outpatient_v001")
    clusters = [_cluster("case1_a")]
    assignments = [
        ClusterAssignmentInput(cluster_id="case1_a", section_ids=["motivo_consulta"])
    ]
    call_section_ids: list[str] = []

    def fake_job(
        job: SectionGenerationJob,
        **kwargs: object,
    ) -> SectionGenerationRun:
        call_section_ids.append(job.section_id)
        return SectionGenerationRun(
            section_id=job.section_id,
            cluster_ids=job.cluster_ids,
            context_present=job.context_present,
            context_chars=job.context_chars,
            result=SectionGenerationResult(
                section_id=job.section_id,
                content="texto",
            ),
            llm_responses=[LlmResponse(content="{}")],
            raw_response="{}",
            response_time_ms=10,
        )

    import generation.generate as generate_module

    monkeypatch.setattr(generate_module, "_run_section_generation_job", fake_job)

    session_run = run_generation_session(
        session_id="case1",
        assignments=assignments,
        clusters=clusters,
        template=template,
        model_spec=type("Spec", (), {"provider": "openai", "model": "x"})(),  # type: ignore[arg-type]
        system_prompt="test",
        section_concurrency=0,
    )

    assert call_section_ids == ["motivo_consulta"]
    assert session_run.section_plan.job_count == 1
    assert session_run.session_result.skipped_sections
