from __future__ import annotations

import pytest

from common.context_spans import (
    Directive,
    DirectiveScope,
    Span,
    SpanKind,
    SpanSelectorResult,
    document_preference_directives,
    resolve_document_target,
    transcript_directives_for_section,
)
from context_pipeline.document_directive_filter.lib import (
    apply_document_directives,
    apply_ignore_source_directives,
)


def _document_directive(**kwargs: object) -> Directive:
    return Directive(scope=DirectiveScope.DOCUMENT, **kwargs)  # type: ignore[arg-type]


def _transcript_directive(**kwargs: object) -> Directive:
    return Directive(scope=DirectiveScope.TRANSCRIPT, **kwargs)  # type: ignore[arg-type]


def test_directive_rejects_transcript_ignore_source() -> None:
    with pytest.raises(ValueError, match="ignore_source_prohibited"):
        _transcript_directive(action="ignore_source", topic="ruido")


def test_directive_limit_to_topic_requires_section_id() -> None:
    with pytest.raises(ValueError, match="requires_section_id"):
        _transcript_directive(action="limit_to_topic", topic="cirugía")


def test_resolve_document_target_matches_fixture_id() -> None:
    assert (
        resolve_document_target("epicrisis", ["case2_epicrisis", "case2_labs"])
        == "case2_epicrisis"
    )


def test_apply_ignore_source_removes_document_spans_without_llm() -> None:
    spans = [
        Span(id="1", doc="case2_epicrisis", kind=SpanKind.LINE, text="a"),
        Span(id="2", doc="case2_labs", kind=SpanKind.LINE, text="b"),
    ]
    directives = [
        _document_directive(
            action="ignore_source",
            target="case2_epicrisis",
        )
    ]
    outcome = apply_document_directives(
        spans,
        directives,
        available_documents=["case2_epicrisis", "case2_labs"],
    )
    assert [span.id for span in outcome.spans] == ["2"]
    assert outcome.ambiguous_directives == []


def test_apply_ignore_source_unresolved_target_is_ambiguous() -> None:
    spans = [Span(id="1", doc="case2_labs", kind=SpanKind.LINE, text="b")]
    directives = [
        _document_directive(
            action="ignore_source",
            target="documento_inventado",
        )
    ]
    outcome = apply_document_directives(
        spans,
        directives,
        available_documents=["case2_labs"],
    )
    assert outcome.spans == spans
    assert len(outcome.ambiguous_directives) == 1
    assert outcome.ambiguous_directives[0].reason == "unresolved_document_target"


def test_apply_limit_source_to_uses_selector_keep_ids() -> None:
    spans = [
        Span(id="1", doc="case2_epicrisis", kind=SpanKind.LINE, text="neumonía"),
        Span(id="2", doc="case2_epicrisis", kind=SpanKind.LINE, text="otro tema"),
        Span(id="3", doc="case2_labs", kind=SpanKind.LINE, text="lab"),
    ]
    directives = [
        _document_directive(
            action="limit_source_to",
            target="case2_epicrisis",
            topic="neumonía",
        )
    ]
    outcome = apply_document_directives(
        spans,
        directives,
        available_documents=["case2_epicrisis", "case2_labs"],
        selector_results=[SpanSelectorResult(keep_ids=["1"])],
    )
    assert [span.id for span in outcome.spans] == ["1", "3"]


def test_document_preference_directives_exclude_filter_actions() -> None:
    directives = [
        _document_directive(action="ignore_source", target="case2_epicrisis"),
        _document_directive(
            action="prefer_topic",
            target="case2_labs",
            topic="anemia",
        ),
    ]
    assert len(document_preference_directives(directives)) == 1
    assert document_preference_directives(directives)[0].action == "prefer_topic"


def test_transcript_directives_for_section_filters_by_section_id() -> None:
    directives = [
        _transcript_directive(
            action="limit_to_topic",
            section_id="antecedentes",
            topic="cirugía",
        ),
        _transcript_directive(
            action="exclude_topic",
            topic="ruido",
        ),
    ]
    scoped = transcript_directives_for_section(directives, "antecedentes")
    assert len(scoped) == 2
    scoped_motivo = transcript_directives_for_section(directives, "motivo_consulta")
    assert len(scoped_motivo) == 1
    assert scoped_motivo[0].action == "exclude_topic"


def test_apply_ignore_source_directives_only() -> None:
    spans = [
        Span(id="1", doc="doc_a", kind=SpanKind.LINE, text="a"),
        Span(id="2", doc="doc_b", kind=SpanKind.LINE, text="b"),
    ]
    filtered, ambiguous = apply_ignore_source_directives(
        spans,
        [_document_directive(action="ignore_source", target="doc_a")],
        available_documents=["doc_a", "doc_b"],
    )
    assert [span.id for span in filtered] == ["2"]
    assert ambiguous == []
