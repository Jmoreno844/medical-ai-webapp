from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

from common.case_paths import CONTEXT_CASES_INDEX
from common.context_spans import (
    apply_span_drops,
    build_adapter_jobs,
    build_spans_from_pdf,
    build_spans_from_text,
    doctor_items_to_spans,
    merge_spans,
    split_doctor_items,
    span_to_payload_item,
)
from common.output_detail import normalize_output_detail
from common.prompts import normalize_prompt_version
from common.templates import DEFAULT_TEMPLATES_DIR, load_template
from context_pipeline.cases.lib import (
    DoctorNoteCase,
    load_context_case,
    load_context_cases,
    load_document_text,
    select_context_case,
)
from context_pipeline.classify_clusters.classify_clusters import run_classify_clusters
from context_pipeline.classify_clusters.lib import enrich_classify_clusters_result_for_export
from context_pipeline.classify_clusters.lib import load_prompt as load_classify_clusters_prompt
from context_pipeline.classify_clusters.lib import (
    classify_clusters_prompt_reference,
)
from context_pipeline.cluster_spans.cluster_spans import run_cluster_spans
from context_pipeline.cluster_spans.lib import enrich_cluster_spans_result_for_export
from context_pipeline.cluster_spans.lib import load_prompt as load_cluster_spans_prompt
from context_pipeline.cluster_spans.lib import (
    cluster_spans_prompt_reference,
)
from context_pipeline.filter_spans.filter_spans import run_filter_spans
from context_pipeline.filter_spans.lib import enrich_filter_spans_result_for_export
from context_pipeline.filter_spans.lib import load_prompt as load_filter_spans_prompt
from context_pipeline.filter_spans.lib import (
    filter_spans_prompt_reference,
)
from context_pipeline.section_adapter.lib import (
    enrich_section_adapter_session_for_export,
    run_section_adapter_session,
)
from context_pipeline.section_adapter.lib import load_prompt as load_section_adapter_prompt
from context_pipeline.section_adapter.lib import (
    section_adapter_prompt_reference,
)
from context_pipeline.session import run_context_pipeline_ad_hoc, run_context_pipeline_session
from context_pipeline.triage.lib import enrich_triage_result_for_export
from context_pipeline.triage.lib import load_prompt as load_triage_prompt
from context_pipeline.triage.lib import prompt_file_path as triage_prompt_file_path
from context_pipeline.triage.triage import run_triage
from ui.discovery import AI_PIPELINE_ROOT

OUTPUT_DETAIL = "compact"
_RUNTIME: tuple[object, ...] | None = None


def _rt() -> tuple[object, ...]:
    global _RUNTIME
    if _RUNTIME is None:
        from ui.runner import (
            PipelineRunOutput,
            StepConfig,
            _persist_results,
            _step_config_metadata,
            apply_step_config_env,
            build_model_spec,
        )

        _RUNTIME = (
            PipelineRunOutput,
            StepConfig,
            _persist_results,
            _step_config_metadata,
            apply_step_config_env,
            build_model_spec,
        )
    return _RUNTIME


def _load_context_case_bundle(
    *,
    context_case_id: str,
    doctor_note_case: DoctorNoteCase | None = None,
) -> tuple[object, object, Path]:
    cases_index = CONTEXT_CASES_INDEX
    if doctor_note_case is not None:
        case_meta = select_context_case(
            load_context_cases(cases_index),
            case_id=context_case_id,
        )
        return case_meta, doctor_note_case, cases_index
    case_meta = select_context_case(
        load_context_cases(cases_index),
        case_id=context_case_id,
    )
    context_case = load_context_case(case_meta, cases_dir=cases_index.parent)
    return case_meta, context_case, cases_index


def _spans_from_prior_record(record: dict[str, object]) -> list:
    from common.context_spans import Span

    spans_raw = record.get("spans")
    if isinstance(spans_raw, list):
        return [Span.model_validate(item) for item in spans_raw if isinstance(item, dict)]
    filtered = record.get("filtered_spans")
    if isinstance(filtered, list):
        return [Span.model_validate(item) for item in filtered if isinstance(item, dict)]
    span_pool = record.get("span_pool")
    if isinstance(span_pool, list):
        return [Span.model_validate(item) for item in span_pool if isinstance(item, dict)]
    raise ValueError("context_prior_record_missing_spans")


def _directives_from_prior_record(record: dict[str, object]):
    from common.context_spans import Directive, TriageResult

    triage = record.get("triage_result")
    if isinstance(triage, dict):
        directives_raw = triage.get("directives")
        if isinstance(directives_raw, list):
            return [Directive.model_validate(item) for item in directives_raw]
        return TriageResult.model_validate(triage).directives
    return []


def _filter_spans_result_export(
    span_pool: list[object],
    filtered_spans: list[object],
) -> dict[str, object]:
    kept_ids = {
        str(span.get("id"))
        for span in filtered_spans
        if isinstance(span, dict) and span.get("id")
    }
    drop_ids = [
        str(span.get("id"))
        for span in span_pool
        if isinstance(span, dict) and span.get("id") and str(span.get("id")) not in kept_ids
    ]
    return {
        "drop_ids": drop_ids,
        "drop_count": len(drop_ids),
        "kept_span_count": len(kept_ids),
    }


def _filter_spans_result_for_run(context_run: object) -> dict[str, object]:
    filter_result = getattr(context_run, "filter_result", None)
    span_pool = getattr(context_run, "span_pool", [])
    filtered_spans = getattr(context_run, "filtered_spans", [])
    if filter_result is not None:
        return enrich_filter_spans_result_for_export(
            filter_result,
            spans=span_pool,
        )
    pool_payload = [span_to_payload_item(span) for span in span_pool]
    filtered_payload = [span_to_payload_item(span) for span in filtered_spans]
    return _filter_spans_result_export(pool_payload, filtered_payload)


def _pipeline_status_fields(context_run: object) -> dict[str, object]:
    pipeline_error = getattr(context_run, "pipeline_error", None)
    if isinstance(pipeline_error, str) and pipeline_error:
        stopped_after = getattr(context_run, "stopped_after_step", None)
        return {
            "pipeline_status": "partial",
            "stopped_after_step": stopped_after,
            "pipeline_error": pipeline_error,
        }
    return {"pipeline_status": "complete"}


def run_context_triage_step(
    *,
    context_case_id: str,
    config: "StepConfig",
    doctor_note_case: DoctorNoteCase | None = None,
) -> "PipelineRunOutput":
    (
        PipelineRunOutput,
        _StepConfig,
        _persist_results,
        _step_config_metadata,
        apply_step_config_env,
        build_model_spec,
    ) = _rt()
    output_detail = normalize_output_detail(OUTPUT_DETAIL)
    prompt_version = normalize_prompt_version(config.prompt_version)
    model_spec = build_model_spec(config.provider, config.model)
    case_meta, bundle, cases_index = _load_context_case_bundle(
        context_case_id=context_case_id,
        doctor_note_case=doctor_note_case,
    )
    if isinstance(bundle, DoctorNoteCase):
        note_text = bundle.doctor_note
        session_id = bundle.session_id
    else:
        note_text = bundle.doctor_note.doctor_note
        session_id = case_meta.session_id

    doctor_items, is_pasted = split_doctor_items(note_text, session_id=session_id)
    run_started_at = datetime.now(UTC)
    results_dir = AI_PIPELINE_ROOT / "context_pipeline" / "triage" / "results"
    output_path = results_dir / (
        f"{run_started_at.strftime('%Y%m%dT%H%M%SZ')}_debug_{context_case_id}_{model_spec.provider}.json"
    )

    with apply_step_config_env(config):
        started_at = time.perf_counter()
        triage_result, llm_response = run_triage(
            session_id=session_id,
            items=doctor_items,
            model_spec=model_spec,
            system_prompt=load_triage_prompt(prompt_version),
        )
        response_time_ms = int((time.perf_counter() - started_at) * 1000)

    result_record: dict[str, object] = {
        "run_mode": "debug",
        "run_started_at": run_started_at.isoformat(),
        "run_finished_at": datetime.now(UTC).isoformat(),
        "output_path": str(output_path),
        "case_id": context_case_id,
        "session_id": session_id,
        "encounter_date": case_meta.encounter_date,
        "is_pasted": is_pasted,
        "doctor_items": [item.model_dump(mode="json") for item in doctor_items],
        "provider": model_spec.provider,
        "model": model_spec.model,
        "response_time_ms": response_time_ms,
        "llm_usage": llm_response.usage,
        "triage_result": enrich_triage_result_for_export(
            triage_result,
            items=doctor_items,
        ),
        "prompt_file": str(
            triage_prompt_file_path(prompt_version).relative_to(
                AI_PIPELINE_ROOT / "context_pipeline" / "triage"
            )
        ),
        "output_detail": output_detail,
        **_step_config_metadata(config),
    }
    _persist_results(output_path, result_record)
    return PipelineRunOutput(
        step="context_triage",
        result_record=result_record,
        output_path=output_path,
    )


def _build_span_pool_for_case(
    *,
    context_case_id: str,
    triage_record: dict[str, object],
    include_doctor_note: bool = True,
    include_documents: bool = True,
) -> list:
    from common.context_spans import DoctorItem, TriageResult

    cases_index = CONTEXT_CASES_INDEX
    case_meta = select_context_case(
        load_context_cases(cases_index),
        case_id=context_case_id,
    )
    context_case = load_context_case(case_meta, cases_dir=cases_index.parent)
    triage_raw = triage_record.get("triage_result")
    if not isinstance(triage_raw, dict):
        raise ValueError("context_filter_requires_triage_result")
    triage_result = TriageResult.model_validate(triage_raw)
    is_pasted = bool(triage_record.get("is_pasted"))
    items_raw = triage_record.get("doctor_items", [])
    doctor_items = [
        DoctorItem.model_validate(item)
        for item in items_raw
        if isinstance(item, dict)
    ]
    if not doctor_items:
        doctor_items, is_pasted = split_doctor_items(
            context_case.doctor_note.doctor_note,
            session_id=case_meta.session_id,
        )

    span_lists = []
    if include_doctor_note:
        if is_pasted:
            span_lists.append(
                build_spans_from_text(
                    context_case.doctor_note.doctor_note,
                    doc="nota_medico",
                    session_id=case_meta.session_id,
                )
            )
        else:
            span_lists.append(
                doctor_items_to_spans(doctor_items, triage_result.content_ids)
            )
    if include_documents:
        for fixture in context_case.document_fixtures:
            source_path = (cases_index.parent / fixture.source_file).resolve()
            if source_path.suffix.lower() == ".pdf":
                span_lists.append(
                    build_spans_from_pdf(
                        source_path,
                        doc=fixture.document_id,
                        session_id=case_meta.session_id,
                    )
                )
            else:
                span_lists.append(
                    build_spans_from_text(
                        load_document_text(fixture, cases_dir=cases_index.parent),
                        doc=fixture.document_id,
                        session_id=case_meta.session_id,
                    )
                )
    if not span_lists:
        return []
    return merge_spans(*span_lists)


def run_context_filter_spans_step(
    *,
    context_case_id: str,
    config: "StepConfig",
    triage_result_path: Path,
) -> "PipelineRunOutput":
    (
        PipelineRunOutput,
        _StepConfig,
        _persist_results,
        _step_config_metadata,
        apply_step_config_env,
        build_model_spec,
    ) = _rt()
    output_detail = normalize_output_detail(OUTPUT_DETAIL)
    prompt_version = normalize_prompt_version(config.prompt_version)
    model_spec = build_model_spec(config.provider, config.model)
    triage_record = json.loads(triage_result_path.read_text(encoding="utf-8"))
    case_meta = select_context_case(
        load_context_cases(CONTEXT_CASES_INDEX),
        case_id=context_case_id,
    )
    spans = _build_span_pool_for_case(
        context_case_id=context_case_id,
        triage_record=triage_record,
    )
    directives = _directives_from_prior_record(triage_record)
    document_date = None
    context_case = load_context_case(case_meta, cases_dir=CONTEXT_CASES_INDEX.parent)
    for fixture in context_case.document_fixtures:
        if fixture.document_date:
            document_date = fixture.document_date
            break

    run_started_at = datetime.now(UTC)
    results_dir = AI_PIPELINE_ROOT / "context_pipeline" / "filter_spans" / "results"
    output_path = results_dir / (
        f"{run_started_at.strftime('%Y%m%dT%H%M%SZ')}_debug_{context_case_id}_{model_spec.provider}.json"
    )

    with apply_step_config_env(config):
        started_at = time.perf_counter()
        filter_result, llm_response = run_filter_spans(
            encounter_date=case_meta.encounter_date,
            document_date=document_date,
            directives=directives,
            spans=spans,
            model_spec=model_spec,
            system_prompt=load_filter_spans_prompt(prompt_version),
            prompt_version=prompt_version,
        )
        response_time_ms = int((time.perf_counter() - started_at) * 1000)

    filtered_spans = apply_span_drops(spans, filter_result.drop_ids)
    result_record: dict[str, object] = {
        "run_mode": "debug",
        "run_started_at": run_started_at.isoformat(),
        "run_finished_at": datetime.now(UTC).isoformat(),
        "output_path": str(output_path),
        "case_id": context_case_id,
        "session_id": case_meta.session_id,
        "encounter_date": case_meta.encounter_date,
        "provider": model_spec.provider,
        "model": model_spec.model,
        "response_time_ms": response_time_ms,
        "llm_usage": llm_response.usage,
        "span_pool": [span_to_payload_item(span) for span in spans],
        "filter_spans_result": enrich_filter_spans_result_for_export(
            filter_result,
            spans=spans,
        ),
        "filtered_spans": [span_to_payload_item(span) for span in filtered_spans],
        "triage_result_file": str(triage_result_path),
        "prompt_file": filter_spans_prompt_reference(prompt_version),
        "output_detail": output_detail,
        **_step_config_metadata(config),
    }
    _persist_results(output_path, result_record)
    return PipelineRunOutput(
        step="context_filter_spans",
        result_record=result_record,
        output_path=output_path,
    )


def run_context_cluster_spans_step(
    *,
    context_case_id: str,
    config: "StepConfig",
    filter_spans_result_path: Path,
) -> "PipelineRunOutput":
    (
        PipelineRunOutput,
        _StepConfig,
        _persist_results,
        _step_config_metadata,
        apply_step_config_env,
        build_model_spec,
    ) = _rt()
    output_detail = normalize_output_detail(OUTPUT_DETAIL)
    prompt_version = normalize_prompt_version(config.prompt_version)
    model_spec = build_model_spec(config.provider, config.model)
    filter_record = json.loads(filter_spans_result_path.read_text(encoding="utf-8"))
    case_meta = select_context_case(
        load_context_cases(CONTEXT_CASES_INDEX),
        case_id=context_case_id,
    )
    spans = _spans_from_prior_record(filter_record)

    run_started_at = datetime.now(UTC)
    results_dir = AI_PIPELINE_ROOT / "context_pipeline" / "cluster_spans" / "results"
    output_path = results_dir / (
        f"{run_started_at.strftime('%Y%m%dT%H%M%SZ')}_debug_{context_case_id}_{model_spec.provider}.json"
    )

    with apply_step_config_env(config):
        started_at = time.perf_counter()
        clusters, llm_response = run_cluster_spans(
            spans=spans,
            model_spec=model_spec,
            system_prompt=load_cluster_spans_prompt(prompt_version),
            prompt_version=prompt_version,
        )
        response_time_ms = int((time.perf_counter() - started_at) * 1000)

    result_record: dict[str, object] = {
        "run_mode": "debug",
        "run_started_at": run_started_at.isoformat(),
        "run_finished_at": datetime.now(UTC).isoformat(),
        "output_path": str(output_path),
        "case_id": context_case_id,
        "session_id": case_meta.session_id,
        "provider": model_spec.provider,
        "model": model_spec.model,
        "response_time_ms": response_time_ms,
        "llm_usage": llm_response.usage,
        "filtered_spans": [span_to_payload_item(span) for span in spans],
        "cluster_spans_result": enrich_cluster_spans_result_for_export(clusters),
        "filter_spans_result_file": str(filter_spans_result_path),
        "prompt_file": cluster_spans_prompt_reference(prompt_version),
        "output_detail": output_detail,
        **_step_config_metadata(config),
    }
    _persist_results(output_path, result_record)
    return PipelineRunOutput(
        step="context_cluster_spans",
        result_record=result_record,
        output_path=output_path,
    )


def run_context_classify_clusters_step(
    *,
    context_case_id: str,
    config: "StepConfig",
    cluster_spans_result_path: Path,
) -> "PipelineRunOutput":
    (
        PipelineRunOutput,
        _StepConfig,
        _persist_results,
        _step_config_metadata,
        apply_step_config_env,
        build_model_spec,
    ) = _rt()
    output_detail = normalize_output_detail(OUTPUT_DETAIL)
    prompt_version = normalize_prompt_version(config.prompt_version)
    model_spec = build_model_spec(config.provider, config.model)
    cluster_record = json.loads(cluster_spans_result_path.read_text(encoding="utf-8"))
    case_meta = select_context_case(
        load_context_cases(CONTEXT_CASES_INDEX),
        case_id=context_case_id,
    )
    template = load_template(case_meta.template_id, templates_dir=DEFAULT_TEMPLATES_DIR)
    spans = _spans_from_prior_record(cluster_record)
    clusters_raw = cluster_record.get("cluster_spans_result", {})
    if isinstance(clusters_raw, dict):
        clusters_list = clusters_raw.get("clusters", [])
    else:
        clusters_list = []
    from common.context_spans import SpanCluster, propagate_cluster_date_hints

    clusters = [
        SpanCluster.model_validate(item)
        for item in clusters_list
        if isinstance(item, dict)
    ]
    clusters = propagate_cluster_date_hints(clusters, spans)
    context_case = load_context_case(case_meta, cases_dir=CONTEXT_CASES_INDEX.parent)
    document_date = None
    for fixture in context_case.document_fixtures:
        if fixture.document_date:
            document_date = fixture.document_date
            break

    run_started_at = datetime.now(UTC)
    results_dir = AI_PIPELINE_ROOT / "context_pipeline" / "classify_clusters" / "results"
    output_path = results_dir / (
        f"{run_started_at.strftime('%Y%m%dT%H%M%SZ')}_debug_{context_case_id}_{model_spec.provider}.json"
    )

    with apply_step_config_env(config):
        started_at = time.perf_counter()
        classify_result, llm_response = run_classify_clusters(
            template=template,
            clusters=clusters,
            spans=spans,
            model_spec=model_spec,
            system_prompt=load_classify_clusters_prompt(prompt_version),
            encounter_date=case_meta.encounter_date,
            document_date=document_date,
            prompt_version=prompt_version,
        )
        response_time_ms = int((time.perf_counter() - started_at) * 1000)

    result_record: dict[str, object] = {
        "run_mode": "debug",
        "run_started_at": run_started_at.isoformat(),
        "run_finished_at": datetime.now(UTC).isoformat(),
        "output_path": str(output_path),
        "case_id": context_case_id,
        "session_id": case_meta.session_id,
        "template_id": case_meta.template_id,
        "provider": model_spec.provider,
        "model": model_spec.model,
        "response_time_ms": response_time_ms,
        "llm_usage": llm_response.usage,
        "filtered_spans": [span_to_payload_item(span) for span in spans],
        "cluster_spans_result": enrich_cluster_spans_result_for_export(clusters),
        "classify_clusters_result": enrich_classify_clusters_result_for_export(
            classify_result,
            template=template,
        ),
        "classify_clusters_assignments": [
            assignment.model_dump(mode="json")
            for assignment in classify_result.assignments
        ],
        "cluster_spans_result_file": str(cluster_spans_result_path),
        "prompt_file": classify_clusters_prompt_reference(prompt_version),
        "output_detail": output_detail,
        **_step_config_metadata(config),
    }
    _persist_results(output_path, result_record)
    return PipelineRunOutput(
        step="context_classify_clusters",
        result_record=result_record,
        output_path=output_path,
    )


def run_context_section_adapter_step(
    *,
    context_case_id: str,
    config: "StepConfig",
    classify_clusters_result_path: Path,
) -> "PipelineRunOutput":
    (
        PipelineRunOutput,
        _StepConfig,
        _persist_results,
        _step_config_metadata,
        apply_step_config_env,
        build_model_spec,
    ) = _rt()
    output_detail = normalize_output_detail(OUTPUT_DETAIL)
    prompt_version = normalize_prompt_version(config.prompt_version)
    model_spec = build_model_spec(config.provider, config.model)
    classify_record = json.loads(
        classify_clusters_result_path.read_text(encoding="utf-8")
    )
    case_meta = select_context_case(
        load_context_cases(CONTEXT_CASES_INDEX),
        case_id=context_case_id,
    )
    template = load_template(case_meta.template_id, templates_dir=DEFAULT_TEMPLATES_DIR)
    spans = _spans_from_prior_record(classify_record)
    clusters_raw = classify_record.get("cluster_spans_result", {})
    clusters_list = (
        clusters_raw.get("clusters", [])
        if isinstance(clusters_raw, dict)
        else []
    )
    from common.context_spans import ClassifyClustersResult, SpanCluster

    clusters = [
        SpanCluster.model_validate(item)
        for item in clusters_list
        if isinstance(item, dict)
    ]
    assignments_raw = classify_record.get("classify_clusters_assignments")
    if isinstance(assignments_raw, dict):
        classify_result = ClassifyClustersResult(assignments=assignments_raw)
    elif isinstance(assignments_raw, list):
        classify_result = ClassifyClustersResult(assignments=assignments_raw)
    else:
        raise ValueError("context_section_adapter_requires_classify_assignments")
    directives = _directives_from_prior_record(classify_record)
    adapter_jobs = build_adapter_jobs(classify_result, template.section_id_set())
    context_case = load_context_case(case_meta, cases_dir=CONTEXT_CASES_INDEX.parent)
    document_date = None
    for fixture in context_case.document_fixtures:
        if fixture.document_date:
            document_date = fixture.document_date
            break

    run_started_at = datetime.now(UTC)
    results_dir = AI_PIPELINE_ROOT / "context_pipeline" / "section_adapter" / "results"
    output_path = results_dir / (
        f"{run_started_at.strftime('%Y%m%dT%H%M%SZ')}_debug_{context_case_id}_{model_spec.provider}.json"
    )

    with apply_step_config_env(config):
        adapter_session = run_section_adapter_session(
            adapter_jobs=adapter_jobs,
            clusters=clusters,
            spans=spans,
            template=template,
            encounter_date=case_meta.encounter_date,
            document_date=case_meta.document_date,
            directives=directives,
            model_spec=model_spec,
            system_prompt=load_section_adapter_prompt(prompt_version),
            prompt_version=prompt_version,
        )

    result_record: dict[str, object] = {
        "run_mode": "debug",
        "run_started_at": run_started_at.isoformat(),
        "run_finished_at": datetime.now(UTC).isoformat(),
        "output_path": str(output_path),
        "case_id": context_case_id,
        "session_id": case_meta.session_id,
        "template_id": case_meta.template_id,
        "provider": model_spec.provider,
        "model": model_spec.model,
        "total_response_time_ms": adapter_session.total_response_time_ms,
        "section_execution_mode": adapter_session.section_execution_mode,
        "llm_usage_summary": adapter_session.llm_usage_summary,
        "section_adapter_result": enrich_section_adapter_session_for_export(
            adapter_session.section_context
        ),
        "section_context": adapter_session.section_context,
        "classify_clusters_result_file": str(classify_clusters_result_path),
        "prompt_file": section_adapter_prompt_reference(prompt_version),
        "output_detail": output_detail,
        **_step_config_metadata(config),
    }
    _persist_results(output_path, result_record)
    return PipelineRunOutput(
        step="context_section_adapter",
        result_record=result_record,
        output_path=output_path,
    )


def run_context_pipeline_step(
    *,
    context_case_id: str,
    config: "StepConfig",
    include_doctor_note: bool = True,
    include_documents: bool = True,
) -> "PipelineRunOutput":
    (
        PipelineRunOutput,
        _StepConfig,
        _persist_results,
        _step_config_metadata,
        apply_step_config_env,
        build_model_spec,
    ) = _rt()
    output_detail = normalize_output_detail(OUTPUT_DETAIL)
    prompt_version = normalize_prompt_version(config.prompt_version)
    model_spec = build_model_spec(config.provider, config.model)
    cases_index = CONTEXT_CASES_INDEX
    run_started_at = datetime.now(UTC)
    results_dir = AI_PIPELINE_ROOT / "context_pipeline" / "section_adapter" / "results"
    output_path = results_dir / (
        f"{run_started_at.strftime('%Y%m%dT%H%M%SZ')}_context_{context_case_id}_{model_spec.provider}.json"
    )

    with apply_step_config_env(config):
        context_run = run_context_pipeline_session(
            case_id=context_case_id,
            cases_index=cases_index,
            templates_dir=DEFAULT_TEMPLATES_DIR,
            model_spec=model_spec,
            triage_prompt=load_triage_prompt(prompt_version),
            filter_spans_prompt=load_filter_spans_prompt(prompt_version),
            filter_spans_prompt_version=prompt_version,
            cluster_spans_prompt=load_cluster_spans_prompt(prompt_version),
            cluster_spans_prompt_version=prompt_version,
            classify_clusters_prompt=load_classify_clusters_prompt(prompt_version),
            classify_clusters_prompt_version=prompt_version,
            section_adapter_prompt=load_section_adapter_prompt(prompt_version),
            section_adapter_prompt_version=prompt_version,
            include_doctor_note=include_doctor_note,
            include_documents=include_documents,
        )

    template = load_template(
        context_run.template_id,
        templates_dir=DEFAULT_TEMPLATES_DIR,
    )
    result_record: dict[str, object] = {
        "run_mode": "context_pipeline_session",
        "run_started_at": run_started_at.isoformat(),
        "run_finished_at": datetime.now(UTC).isoformat(),
        "output_path": str(output_path),
        "case_id": context_case_id,
        "session_id": context_run.session_id,
        "template_id": context_run.template_id,
        "encounter_date": context_run.encounter_date,
        "include_doctor_note": include_doctor_note,
        "include_documents": include_documents,
        "is_pasted": context_run.is_pasted,
        "provider": model_spec.provider,
        "model": model_spec.model,
        "doctor_items": [
            item.model_dump(mode="json") for item in context_run.doctor_items
        ],
        "triage_result": enrich_triage_result_for_export(
            context_run.triage_result,
            items=context_run.doctor_items,
        ),
        "span_pool": [
            span_to_payload_item(span) for span in context_run.span_pool
        ],
        "filter_spans_result": _filter_spans_result_for_run(context_run),
        "filtered_spans": [
            span_to_payload_item(span) for span in context_run.filtered_spans
        ],
        "cluster_spans_result": enrich_cluster_spans_result_for_export(
            context_run.clusters
        ),
        "classify_clusters_result": enrich_classify_clusters_result_for_export(
            context_run.classify_result,
            template=template,
        ),
        "classify_clusters_assignments": [
            assignment.model_dump(mode="json")
            for assignment in context_run.classify_result.assignments
        ],
        "adapter_jobs": context_run.adapter_jobs,
        "section_adapter_result": enrich_section_adapter_session_for_export(
            context_run.section_context
        ),
        "section_context": context_run.section_context,
        "llm_calls": [
            {
                "label": call.label,
                "provider": call.provider,
                "model": call.model,
                "llm_usage": call.llm_response.usage,
            }
            for call in context_run.llm_calls
        ],
        "prompt_file": section_adapter_prompt_reference(prompt_version),
        "output_detail": output_detail,
        **_pipeline_status_fields(context_run),
        **_step_config_metadata(config),
    }
    _persist_results(output_path, result_record)
    return PipelineRunOutput(
        step="context_pipeline",
        result_record=result_record,
        output_path=output_path,
    )


def run_context_ad_hoc_pipeline_step(
    *,
    session_id: str,
    template_id: str,
    config: "StepConfig",
    doctor_note: str | None = None,
    document_pdf_path: Path | None = None,
    document_id: str = "uploaded_document",
    encounter_date: str | None = None,
    document_date: str | None = None,
) -> "PipelineRunOutput":
    (
        PipelineRunOutput,
        _StepConfig,
        _persist_results,
        _step_config_metadata,
        apply_step_config_env,
        build_model_spec,
    ) = _rt()
    output_detail = normalize_output_detail(OUTPUT_DETAIL)
    prompt_version = normalize_prompt_version(config.prompt_version)
    model_spec = build_model_spec(config.provider, config.model)
    run_started_at = datetime.now(UTC)
    results_dir = AI_PIPELINE_ROOT / "context_pipeline" / "section_adapter" / "results"
    safe_session = session_id.strip() or "adhoc"
    output_path = results_dir / (
        f"{run_started_at.strftime('%Y%m%dT%H%M%SZ')}_adhoc_{safe_session}_{model_spec.provider}.json"
    )

    with apply_step_config_env(config):
        context_run = run_context_pipeline_ad_hoc(
            session_id=safe_session,
            template_id=template_id,
            templates_dir=DEFAULT_TEMPLATES_DIR,
            model_spec=model_spec,
            triage_prompt=load_triage_prompt(prompt_version),
            filter_spans_prompt=load_filter_spans_prompt(prompt_version),
            filter_spans_prompt_version=prompt_version,
            cluster_spans_prompt=load_cluster_spans_prompt(prompt_version),
            cluster_spans_prompt_version=prompt_version,
            classify_clusters_prompt=load_classify_clusters_prompt(prompt_version),
            classify_clusters_prompt_version=prompt_version,
            section_adapter_prompt=load_section_adapter_prompt(prompt_version),
            section_adapter_prompt_version=prompt_version,
            doctor_note=doctor_note,
            document_pdf_path=document_pdf_path,
            document_id=document_id,
            encounter_date=encounter_date,
            document_date=document_date,
        )

    template = load_template(template_id, templates_dir=DEFAULT_TEMPLATES_DIR)
    result_record: dict[str, object] = {
        "run_mode": "adhoc_context_pipeline",
        "run_started_at": run_started_at.isoformat(),
        "run_finished_at": datetime.now(UTC).isoformat(),
        "output_path": str(output_path),
        "session_id": context_run.session_id,
        "template_id": context_run.template_id,
        "encounter_date": context_run.encounter_date,
        "document_date": document_date,
        "document_id": document_id if document_pdf_path else None,
        "has_doctor_note": bool(doctor_note and doctor_note.strip()),
        "has_document_pdf": document_pdf_path is not None,
        "is_pasted": context_run.is_pasted,
        "provider": model_spec.provider,
        "model": model_spec.model,
        "doctor_items": [
            item.model_dump(mode="json") for item in context_run.doctor_items
        ],
        "triage_result": enrich_triage_result_for_export(
            context_run.triage_result,
            items=context_run.doctor_items,
        ),
        "span_pool": [
            span_to_payload_item(span) for span in context_run.span_pool
        ],
        "filter_spans_result": _filter_spans_result_for_run(context_run),
        "filtered_spans": [
            span_to_payload_item(span) for span in context_run.filtered_spans
        ],
        "cluster_spans_result": enrich_cluster_spans_result_for_export(
            context_run.clusters
        ),
        "classify_clusters_result": enrich_classify_clusters_result_for_export(
            context_run.classify_result,
            template=template,
        ),
        "classify_clusters_assignments": [
            assignment.model_dump(mode="json")
            for assignment in context_run.classify_result.assignments
        ],
        "adapter_jobs": context_run.adapter_jobs,
        "section_adapter_result": enrich_section_adapter_session_for_export(
            context_run.section_context
        ),
        "section_context": context_run.section_context,
        "llm_calls": [
            {
                "label": call.label,
                "provider": call.provider,
                "model": call.model,
                "llm_usage": call.llm_response.usage,
            }
            for call in context_run.llm_calls
        ],
        "prompt_file": section_adapter_prompt_reference(prompt_version),
        "output_detail": output_detail,
        **_pipeline_status_fields(context_run),
        **_step_config_metadata(config),
    }
    _persist_results(output_path, result_record)
    return PipelineRunOutput(
        step="context_ad_hoc_pipeline",
        result_record=result_record,
        output_path=output_path,
    )


__all__ = [
    "run_context_ad_hoc_pipeline_step",
    "run_context_classify_clusters_step",
    "run_context_cluster_spans_step",
    "run_context_filter_spans_step",
    "run_context_pipeline_step",
    "run_context_section_adapter_step",
    "run_context_triage_step",
]
