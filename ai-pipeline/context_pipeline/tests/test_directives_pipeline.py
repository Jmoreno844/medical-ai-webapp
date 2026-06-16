from __future__ import annotations

from common.context_spans import (
    Directive,
    DirectiveScope,
    Span,
    SpanKind,
    TriageResult,
)
from context_pipeline.span_pool import (
    build_approved_note_spans,
    merge_approved_and_filtered_document_spans,
)
from context_pipeline.triage.lib import parse_triage_result


def test_parse_triage_result_accepts_scoped_directives() -> None:
    raw = """
    {
      "directives": [
        {
          "scope": "document",
          "action": "ignore_source",
          "target": "case2_epicrisis"
        }
      ],
      "content_ids": [3],
      "drop_ids": [1]
    }
    """
    result = parse_triage_result(raw)
    assert result.content_ids == ["3"]
    assert result.directives[0].scope == DirectiveScope.DOCUMENT


def test_approved_note_spans_bypass_document_filter_merge() -> None:
    note_spans = [
        Span(id="1", doc="nota_medico", kind=SpanKind.LINE, text="alergia"),
    ]
    document_spans = [
        Span(id="1", doc="case2_labs", kind=SpanKind.LINE, text="hb"),
    ]
    merged = merge_approved_and_filtered_document_spans(
        approved_note_spans=note_spans,
        filtered_document_spans=document_spans,
    )
    assert len(merged) == 2
    assert {span.doc for span in merged} == {"nota_medico", "case2_labs"}


def test_build_approved_note_spans_from_triage_content_ids() -> None:
    from common.context_spans import DoctorItem

    items = [
        DoctorItem(id="1", text="Alergia."),
        DoctorItem(id="2", text="Meta instrucción."),
    ]
    triage = TriageResult(content_ids=["1"], drop_ids=["2"])
    spans = build_approved_note_spans(
        doctor_note_text="Alergia.\nMeta instrucción.",
        session_id="s1",
        doctor_items=items,
        triage_result=triage,
        is_pasted=False,
        include_doctor_note=True,
    )
    assert len(spans) == 1
    assert spans[0].doc == "nota_medico"


def test_plan_section_generation_attaches_transcript_constraints() -> None:
    from classification.lib import ClusterCase
    from common.templates import load_template
    from generation.lib import ClusterAssignmentInput, plan_section_generation

    template = load_template("minimal_outpatient_v001")
    cluster = ClusterCase(
        id="c1",
        cluster_json={
            "turns": [{"turn_id": 1, "speaker": "PACIENTE", "text": "dolor"}]
        },
        template_id="minimal_outpatient_v001",
    )
    assignments = [
        ClusterAssignmentInput(
            cluster_id="c1",
            section_ids=["motivo_consulta"],
        )
    ]
    directives = [
        Directive(
            scope=DirectiveScope.TRANSCRIPT,
            action="limit_to_topic",
            section_id="motivo_consulta",
            topic="dolor",
        )
    ]
    plan = plan_section_generation(
        assignments,
        {"c1": cluster},
        template,
        transcript_directives=directives,
    )
    job = next(job for job in plan.jobs if job.section_id == "motivo_consulta")
    assert len(job.transcript_constraints) == 1
    assert job.transcript_constraints[0].topic == "dolor"
