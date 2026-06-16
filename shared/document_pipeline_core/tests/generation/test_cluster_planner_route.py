from __future__ import annotations

import json
import threading
import time
from unittest.mock import patch

import pytest

from document_pipeline_core.classification.lib import ClusterCase
from document_pipeline_core.classification.templates import load_template
from document_pipeline_core.common.llm_response import LlmResponse
from document_pipeline_core.common.providers import ModelSpec
from document_pipeline_core.generation.generate import (
    run_cluster_planner_section_generation,
    run_generation_session,
    run_section_generation,
)
from document_pipeline_core.generation.lib import (
    GENERATION_ROUTE_CLUSTER_PLANNER,
    GENERATION_ROUTE_DIRECT,
    GENERATION_ROUTE_TWO_STEP,
    ClusterAssignmentInput,
    GenerationValidationError,
    SectionGenerationJob,
    resolve_generation_route,
    should_use_cluster_planner_generation,
    should_use_two_step_generation,
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
    template_id: str = "minimal_outpatient_v001",
    *,
    clusters: list[ClusterCase] | None = None,
    context: str = "",
) -> SectionGenerationJob:
    template = load_template(template_id)
    section = next(s for s in template.sections if s.section_id == "motivo_consulta")
    resolved_clusters = [_cluster("case1_a")] if clusters is None else clusters
    return SectionGenerationJob(
        section_id=section.section_id,
        section=section,
        clusters=resolved_clusters,
        context=context,
    )


def test_resolve_generation_route_explicit_and_legacy() -> None:
    assert resolve_generation_route(generation_route="direct") == GENERATION_ROUTE_DIRECT
    assert (
        resolve_generation_route(generation_route="two_step") == GENERATION_ROUTE_TWO_STEP
    )
    assert (
        resolve_generation_route(generation_route="cluster_planner")
        == GENERATION_ROUTE_CLUSTER_PLANNER
    )
    assert (
        resolve_generation_route(linked_evidence_two_step=True)
        == GENERATION_ROUTE_TWO_STEP
    )
    assert resolve_generation_route() == GENERATION_ROUTE_DIRECT


def test_should_use_route_helpers() -> None:
    job = _section_job()
    assert should_use_two_step_generation(
        job,
        generation_route=GENERATION_ROUTE_TWO_STEP,
    )
    assert should_use_cluster_planner_generation(
        generation_route=GENERATION_ROUTE_CLUSTER_PLANNER,
    )
    assert not should_use_two_step_generation(job, generation_route=GENERATION_ROUTE_DIRECT)


def _llm_response(content: str) -> LlmResponse:
    return LlmResponse(
        content=content,
        thinking=None,
        thinking_source=None,
        usage={"input_tokens": 1, "output_tokens": 1},
        request_params={},
        timing=None,
    )


def test_cluster_planner_runs_one_subplanner_per_cluster() -> None:
    job = _section_job(
        clusters=[_cluster("case1_a", turn_id=0), _cluster("case1_b", turn_id=10)],
    )
    template = load_template("minimal_outpatient_v001")
    model_spec = ModelSpec(alias="openai", provider="openai", model="gpt-5.4-mini")

    planner_payload_a = json.dumps(
        {"items": [{"text": "Dolor leve.", "e": ["t0"]}]},
        ensure_ascii=False,
    )
    planner_payload_b = json.dumps(
        {"items": [{"text": "Otro dato.", "e": ["t10"]}]},
        ensure_ascii=False,
    )
    renderer_text = "Paciente con dolor leve y otro dato. {{e:t0,t10}}"

    def fake_call(**kwargs: object) -> LlmResponse:
        user = str(kwargs.get("user", ""))
        schema = kwargs.get("output_schema")
        properties = (
            schema.get("properties", {})
            if isinstance(schema, dict)
            else {}
        )
        if "items" in properties:
            if "case1_a" in user:
                return _llm_response(planner_payload_a)
            return _llm_response(planner_payload_b)
        return _llm_response(renderer_text)

    with patch(
        "document_pipeline_core.generation.generate.call_generation_llm_detailed",
        side_effect=fake_call,
    ):
        (
            result,
            responses,
            _ms,
            route,
            _items,
            _block,
            cluster_runs,
            combined_block,
            renderer_raw,
            prompt_files,
            renderer_skipped,
        ) = run_cluster_planner_section_generation(
            job=job,
            template=template,
            model_spec=model_spec,
            prompt_version="v001",
            cluster_planner_concurrency=1,
        )

    assert route == GENERATION_ROUTE_CLUSTER_PLANNER
    assert len(responses) == 3
    assert cluster_runs is not None
    assert len(cluster_runs) == 2
    assert {run["cluster_id"] for run in cluster_runs} == {"case1_a", "case1_b"}
    assert combined_block is not None
    assert "case1_a" in combined_block
    assert "case1_b" in combined_block
    assert renderer_raw is not None
    assert prompt_files is not None
    assert renderer_skipped is False
    assert "{{e:t0,t10}}" in result.content
    assert result.content.strip()


def test_cluster_planner_subplanners_run_in_parallel() -> None:
    job = _section_job(
        clusters=[
            _cluster("case1_a", turn_id=0),
            _cluster("case1_b", turn_id=10),
            _cluster("case1_c", turn_id=20),
        ],
    )
    template = load_template("minimal_outpatient_v001")
    model_spec = ModelSpec(alias="openai", provider="openai", model="gpt-5.4-mini")
    renderer_text = "Texto final. {{e:t0,t10,t20}}"
    active_calls = 0
    max_active_calls = 0
    lock = threading.Lock()

    def fake_call(**kwargs: object) -> LlmResponse:
        nonlocal active_calls, max_active_calls
        user = str(kwargs.get("user", ""))
        schema = kwargs.get("output_schema")
        properties = (
            schema.get("properties", {})
            if isinstance(schema, dict)
            else {}
        )
        if "items" not in properties:
            return _llm_response(renderer_text)
        turn_id = "0"
        if "case1_b" in user:
            turn_id = "10"
        elif "case1_c" in user:
            turn_id = "20"
        payload = json.dumps(
            {"items": [{"text": "Dato.", "e": [f"t{turn_id}"]}]},
            ensure_ascii=False,
        )
        with lock:
            active_calls += 1
            max_active_calls = max(max_active_calls, active_calls)
        time.sleep(0.03)
        with lock:
            active_calls -= 1
        return _llm_response(payload)

    with patch(
        "document_pipeline_core.generation.generate.call_generation_llm_detailed",
        side_effect=fake_call,
    ):
        run_cluster_planner_section_generation(
            job=job,
            template=template,
            model_spec=model_spec,
            prompt_version="v001",
            cluster_planner_concurrency=0,
        )

    assert max_active_calls >= 2


def test_cluster_planner_renderer_rejects_invalid_evidence_ids() -> None:
    job = _section_job(clusters=[_cluster("case1_a")])
    template = load_template("minimal_outpatient_v001")
    model_spec = ModelSpec(alias="openai", provider="openai", model="gpt-5.4-mini")
    planner_payload = json.dumps(
        {"items": [{"text": "Dolor.", "e": ["t0"]}]},
        ensure_ascii=False,
    )
    invalid_renderer_text = "Dolor. {{e:t999}}"

    def fake_call(**kwargs: object) -> LlmResponse:
        schema = kwargs.get("output_schema")
        properties = (
            schema.get("properties", {})
            if isinstance(schema, dict)
            else {}
        )
        if "items" in properties:
            return _llm_response(planner_payload)
        return _llm_response(invalid_renderer_text)

    with patch(
        "document_pipeline_core.generation.generate.call_generation_llm_detailed",
        side_effect=fake_call,
    ):
        with pytest.raises(GenerationValidationError):
            run_cluster_planner_section_generation(
                job=job,
                template=template,
                model_spec=model_spec,
                prompt_version="v001",
            )


def test_cluster_planner_renderer_with_context_cites_c1() -> None:
    job = _section_job(clusters=[], context="Epicrisis previa: anemia.")
    template = load_template("minimal_outpatient_v001")
    model_spec = ModelSpec(alias="openai", provider="openai", model="gpt-5.4-mini")
    renderer_text = "Control por anemia previa. {{e:c1}}"

    with patch(
        "document_pipeline_core.generation.generate.call_generation_llm_detailed",
        return_value=_llm_response(renderer_text),
    ):
        result, *_rest = run_cluster_planner_section_generation(
            job=job,
            template=template,
            model_spec=model_spec,
            prompt_version="v001",
        )

    assert "{{e:c1}}" in result.content


def test_cluster_planner_context_only_section_skips_subplanners() -> None:
    job = _section_job(clusters=[], context="Epicrisis previa: anemia.")
    template = load_template("minimal_outpatient_v001")
    model_spec = ModelSpec(alias="openai", provider="openai", model="gpt-5.4-mini")
    renderer_text = "Control por anemia previa. {{e:c1}}"

    with patch(
        "document_pipeline_core.generation.generate.call_generation_llm_detailed",
        return_value=_llm_response(renderer_text),
    ):
        (
            _result,
            responses,
            _ms,
            route,
            _items,
            _block,
            cluster_runs,
            combined_block,
            _renderer_raw,
            _prompt_files,
            renderer_skipped,
        ) = run_cluster_planner_section_generation(
            job=job,
            template=template,
            model_spec=model_spec,
            prompt_version="v001",
        )

    assert route == GENERATION_ROUTE_CLUSTER_PLANNER
    assert len(responses) == 1
    assert cluster_runs == []
    assert combined_block == "(sin planes por cluster)"
    assert renderer_skipped is False


def test_cluster_planner_skips_renderer_when_all_planners_empty_no_context() -> None:
    job = _section_job(clusters=[_cluster("case1_a"), _cluster("case1_b", turn_id=10)])
    template = load_template("minimal_outpatient_v001")
    model_spec = ModelSpec(alias="openai", provider="openai", model="gpt-5.4-mini")
    empty_planner_payload = json.dumps({"items": []}, ensure_ascii=False)

    with patch(
        "document_pipeline_core.generation.generate.call_generation_llm_detailed",
        return_value=_llm_response(empty_planner_payload),
    ) as mocked:
        (
            result,
            responses,
            _ms,
            route,
            _items,
            _block,
            cluster_runs,
            combined_block,
            renderer_raw,
            _prompt_files,
            renderer_skipped,
        ) = run_cluster_planner_section_generation(
            job=job,
            template=template,
            model_spec=model_spec,
            prompt_version="v001",
        )

    assert mocked.call_count == 2
    assert route == GENERATION_ROUTE_CLUSTER_PLANNER
    assert len(responses) == 2
    assert cluster_runs is not None
    assert len(cluster_runs) == 2
    assert combined_block is not None
    assert "case1_a" in combined_block
    assert "case1_b" in combined_block
    assert renderer_raw is None
    assert renderer_skipped is True
    assert result.content == ""


def test_cluster_planner_runs_renderer_when_all_planners_empty_with_context() -> None:
    job = _section_job(
        clusters=[_cluster("case1_a")],
        context="Epicrisis previa: anemia.",
    )
    template = load_template("minimal_outpatient_v001")
    model_spec = ModelSpec(alias="openai", provider="openai", model="gpt-5.4-mini")
    empty_planner_payload = json.dumps({"items": []}, ensure_ascii=False)
    renderer_text = "Control por anemia previa. {{e:c1}}"
    call_index = 0

    def fake_call(**_kwargs: object) -> LlmResponse:
        nonlocal call_index
        call_index += 1
        if call_index == 1:
            return _llm_response(empty_planner_payload)
        return _llm_response(renderer_text)

    with patch(
        "document_pipeline_core.generation.generate.call_generation_llm_detailed",
        side_effect=fake_call,
    ) as mocked:
        (
            result,
            responses,
            _ms,
            route,
            _items,
            _block,
            cluster_runs,
            _combined_block,
            renderer_raw,
            _prompt_files,
            renderer_skipped,
        ) = run_cluster_planner_section_generation(
            job=job,
            template=template,
            model_spec=model_spec,
            prompt_version="v001",
        )

    assert mocked.call_count == 2
    assert route == GENERATION_ROUTE_CLUSTER_PLANNER
    assert len(responses) == 2
    assert cluster_runs is not None
    assert len(cluster_runs) == 1
    assert renderer_raw is not None
    assert renderer_skipped is False
    assert result.content.strip()


def test_cluster_planner_subplanner_error_includes_cluster_id() -> None:
    job = _section_job(clusters=[_cluster("case1_a")])
    template = load_template("minimal_outpatient_v001")
    model_spec = ModelSpec(alias="openai", provider="openai", model="gpt-5.4-mini")

    def fake_call(**_kwargs: object) -> LlmResponse:
        raise ValueError("planner_failed")

    with patch(
        "document_pipeline_core.generation.generate.call_generation_llm_detailed",
        side_effect=fake_call,
    ):
        with pytest.raises(GenerationValidationError) as exc_info:
            run_cluster_planner_section_generation(
                job=job,
                template=template,
                model_spec=model_spec,
                prompt_version="v001",
            )

    assert exc_info.value.cluster_id == "case1_a"
    assert exc_info.value.generation_substep == "cluster_planner"


def test_cluster_multilabel_runs_separate_subplanners_per_section() -> None:
    template = load_template("minimal_outpatient_v001")
    clusters = [_cluster("shared_cluster")]
    assignments = [
        ClusterAssignmentInput(
            cluster_id="shared_cluster",
            section_ids=["motivo_consulta", "enfermedad_actual"],
        ),
    ]
    model_spec = ModelSpec(alias="openai", provider="openai", model="gpt-5.4-mini")

    planner_payload = json.dumps(
        {"items": [{"text": "Dato.", "e": ["t0"]}]},
        ensure_ascii=False,
    )
    renderer_payload_motivo = "Motivo. {{e:t0}}"
    renderer_payload_enf = "Enfermedad. {{e:t0}}"
    call_index = 0

    def fake_call(**_kwargs: object) -> LlmResponse:
        nonlocal call_index
        call_index += 1
        if call_index in {1, 3}:
            return _llm_response(planner_payload)
        if call_index == 2:
            return _llm_response(renderer_payload_motivo)
        return _llm_response(renderer_payload_enf)

    with patch(
        "document_pipeline_core.generation.generate.call_generation_llm_detailed",
        side_effect=fake_call,
    ):
        session_run = run_generation_session(
            session_id="case1",
            assignments=assignments,
            clusters=clusters,
            template=template,
            model_spec=model_spec,
            system_prompt="ignored",
            prompt_version="v001",
            generation_route=GENERATION_ROUTE_CLUSTER_PLANNER,
            section_concurrency=1,
            cluster_planner_concurrency=1,
        )

    planner_counts = [
        len(run.cluster_planner_runs or [])
        for run in session_run.section_runs
    ]
    assert planner_counts.count(1) == 2


def test_direct_route_unchanged_with_explicit_route() -> None:
    job = _section_job()
    template = load_template("minimal_outpatient_v001")
    model_spec = ModelSpec(alias="openai", provider="openai", model="gpt-5.4-mini")
    direct_payload = json.dumps(
        {"section_id": "motivo_consulta", "content": "Consulta por dolor."},
        ensure_ascii=False,
    )

    with patch(
        "document_pipeline_core.generation.generate.call_generation_llm_detailed",
        return_value=_llm_response(direct_payload),
    ):
        (
            _result,
            responses,
            _ms,
            route,
            planner_items,
            planned_block,
            cluster_runs,
            _combined,
            _renderer_raw,
            prompt_files,
            renderer_skipped,
        ) = run_section_generation(
            job=job,
            template=template,
            model_spec=model_spec,
            system_prompt="ignored",
            prompt_version="v001",
            generation_route=GENERATION_ROUTE_DIRECT,
        )

    assert route == GENERATION_ROUTE_DIRECT
    assert len(responses) == 1
    assert planner_items is None
    assert planned_block is None
    assert cluster_runs is None
    assert prompt_files is not None
    assert renderer_skipped is False
