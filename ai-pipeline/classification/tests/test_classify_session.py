from __future__ import annotations

import threading
import time

import pytest

from classification.batching import ClassificationBatch
from classification.classify import (
    ClassificationBatchRun,
    run_classification_session,
)
from classification.lib import (
    ClassificationBatchResult,
    ClusterAssignment,
    ClusterCase,
)
from classification.templates import load_template
from common.llm_response import LlmResponse
from common.providers import ModelSpec


def _cluster(case_id: str) -> ClusterCase:
    return ClusterCase(
        id=case_id,
        template_id="minimal_outpatient_v001",
        cluster_json={
            "topic_label": case_id,
            "turns": [
                {"turn_id": 0, "speaker": "PACIENTE", "text": f"tema {case_id}"},
            ],
        },
    )


def _batch_run(batch: ClassificationBatch) -> ClassificationBatchRun:
    cluster_id = batch.clusters[0].id
    return ClassificationBatchRun(
        batch_index=batch.batch_index,
        clusters=batch.clusters,
        result=ClassificationBatchResult(
            assignments=[
                ClusterAssignment(
                    cluster_id=cluster_id,
                    section_ids=["motivo_consulta"],
                )
            ]
        ),
        llm_response=LlmResponse(content="{}"),
        raw_response="{}",
        assignment_audit=type(
            "Audit",
            (),
            {"to_dict": lambda self: {"is_valid": True}},
        )(),  # type: ignore[arg-type]
        response_time_ms=200,
    )


def test_run_classification_session_runs_batches_in_parallel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template = load_template("minimal_outpatient_v001")
    clusters = [_cluster("case1_a"), _cluster("case1_b")]
    active_calls = 0
    max_active_calls = 0
    lock = threading.Lock()
    sleep_seconds = 0.2

    def fake_job(
        batch: ClassificationBatch,
        **kwargs: object,
    ) -> ClassificationBatchRun:
        nonlocal active_calls, max_active_calls
        with lock:
            active_calls += 1
            max_active_calls = max(max_active_calls, active_calls)
        time.sleep(sleep_seconds)
        with lock:
            active_calls -= 1
        return _batch_run(batch)

    import classification.classify as classify_module

    monkeypatch.setattr(classify_module, "_run_classification_batch_job", fake_job)
    monkeypatch.setattr(
        classify_module,
        "plan_balanced_batches",
        lambda _clusters, _template, **kwargs: type(
            "Plan",
            (),
            {
                "batches": [
                    ClassificationBatch(
                        batch_index=0,
                        clusters=[clusters[0]],
                        estimated_input_tokens=100,
                    ),
                    ClassificationBatch(
                        batch_index=1,
                        clusters=[clusters[1]],
                        estimated_input_tokens=100,
                    ),
                ]
            },
        )(),
    )

    session_run = run_classification_session(
        session_id="case1",
        clusters=clusters,
        template=template,
        model_spec=ModelSpec(alias="groq", provider="groq", model="qwen/qwen3-32b"),
        system_prompt="test",
        batch_concurrency=0,
    )

    assert session_run.batch_execution_mode == "parallel"
    assert max_active_calls == 2
    assert session_run.total_response_time_ms < int(sleep_seconds * 2000)
    assert session_run.sum_batch_response_time_ms >= int(sleep_seconds * 2000)


def test_run_classification_session_sequential_when_concurrency_is_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template = load_template("minimal_outpatient_v001")
    clusters = [_cluster("case1_a"), _cluster("case1_b")]
    call_order: list[int] = []

    def fake_job(
        batch: ClassificationBatch,
        **kwargs: object,
    ) -> ClassificationBatchRun:
        call_order.append(batch.batch_index)
        return _batch_run(batch)

    import classification.classify as classify_module

    monkeypatch.setattr(classify_module, "_run_classification_batch_job", fake_job)
    monkeypatch.setattr(
        classify_module,
        "plan_balanced_batches",
        lambda _clusters, _template, **kwargs: type(
            "Plan",
            (),
            {
                "batches": [
                    ClassificationBatch(
                        batch_index=0,
                        clusters=[clusters[0]],
                        estimated_input_tokens=100,
                    ),
                    ClassificationBatch(
                        batch_index=1,
                        clusters=[clusters[1]],
                        estimated_input_tokens=100,
                    ),
                ]
            },
        )(),
    )

    session_run = run_classification_session(
        session_id="case1",
        clusters=clusters,
        template=template,
        model_spec=ModelSpec(alias="groq", provider="groq", model="qwen/qwen3-32b"),
        system_prompt="test",
        batch_concurrency=1,
    )

    assert session_run.batch_execution_mode == "sequential"
    assert call_order == [0, 1]
