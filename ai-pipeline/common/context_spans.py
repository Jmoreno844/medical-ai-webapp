from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from common.templates import ClinicalTemplate

_HEADING_HASH_RE = re.compile(r"^#{1,6}\s+.+")
_HEADING_UPPER_RE = re.compile(
    r"^[A-ZÁÉÍÓÚÑ0-9\s\-\.:,;/()]{4,}$",
)
_RESULT_LINE_RE = re.compile(
    r".*\|.*(?:\bVR\b|valor\s+de\s+referencia)",
    re.IGNORECASE,
)
_RESULT_VALUE_RE = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:%|g/dL|mg/dL|mg/L|µg/dL|mmol/L|µmol/L|mEq/L|U/L|UI/L|"
    r"mUI/m[lL]|ng/m[lL]|pg/m[lL]|mL/min|mmHg|/mm³|/mm3|x10\^?\d*)",
    re.IGNORECASE,
)
_REF_RANGE_RE = re.compile(
    r"\bVR\b|valor\s+de\s+referencia|\d+\s*-\s*\d+",
    re.IGNORECASE,
)
_LABEL_LINE_RE = re.compile(
    r"^[\wÁÉÍÓÚÑáéíóúñ][\w .()\-/]{0,40}:\s*\S",
)
_COLUMN_GAP_RE = re.compile(r"\S\s{2,}\S.*\s{2,}\S")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_DATE_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DATE_SLASH_RE = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")
_DATE_DASH_RE = re.compile(r"\b(\d{2})-(\d{2})-(\d{4})\b")
_DATE_MONTH_TEXT_RE = re.compile(
    r"\b(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|"
    r"octubre|noviembre|diciembre)\s+(?:de\s+)?(\d{4})\b",
    re.IGNORECASE,
)
_DATE_RELATIVE_RE = re.compile(
    r"\b(?:desde\s+)?hace\s+(\d+)\s+"
    r"(día|días|semana|semanas|mes|meses|año|años)\b",
    re.IGNORECASE,
)
_DATE_YEAR_IN_RE = re.compile(r"\ben\s+((?:19|20)\d{2})\b", re.IGNORECASE)

PASTED_TOKEN_THRESHOLD = 220
PASTED_LINE_THRESHOLD = 40
PASTED_HEADING_LINE_THRESHOLD = 6
DEFAULT_TOKEN_ENCODING = "cl100k_base"
# Geometría de PDF: hueco mínimo de x0 (px) para tratar el salto como nueva columna.
PDF_COLUMN_GAP = 150.0


class DirectiveAction(StrEnum):
    USE = "use"
    LIMIT_TO = "limit_to"
    IGNORE = "ignore"


class SpanKind(StrEnum):
    PARAGRAPH = "paragraph"
    LINE = "line"
    TABLE_ROW = "table_row"
    HEADING = "heading"
    RESULT_LINE = "result_line"
    UNKNOWN = "unknown"


class DoctorItem(BaseModel):
    id: str
    text: str


class Directive(BaseModel):
    target: str
    action: DirectiveAction
    hint: str | None = None


class TriageResult(BaseModel):
    directives: list[Directive] = Field(default_factory=list)
    content_ids: list[str] = Field(default_factory=list)
    drop_ids: list[str] = Field(default_factory=list)


class Span(BaseModel):
    id: str
    doc: str
    kind: SpanKind
    text: str
    flags: list[str] = Field(default_factory=list)
    date_hint: str | None = None


class FilterSpansResult(BaseModel):
    drop_ids: list[str] = Field(default_factory=list)


class SpanCluster(BaseModel):
    id: str
    span_ids: list[str] = Field(default_factory=list)
    title: str | None = None
    date_hints: list[str] = Field(default_factory=list)


class ClusterClassifyAssignment(BaseModel):
    cluster_id: str
    section_ids: list[str] = Field(default_factory=list)


class ClassifyClustersResult(BaseModel):
    assignments: list[ClusterClassifyAssignment] = Field(default_factory=list)

    @classmethod
    def _normalize_legacy_assignments_dict(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        assignments = data.get("assignments")
        if isinstance(assignments, dict):
            return {
                **data,
                "assignments": [
                    {"cluster_id": cluster_id, "section_ids": section_ids}
                    for cluster_id, section_ids in assignments.items()
                ],
            }
        return data

    @model_validator(mode="before")
    @classmethod
    def normalize_assignments(cls, data: object) -> object:
        return cls._normalize_legacy_assignments_dict(data)

    def assignments_by_cluster_id(self) -> dict[str, list[str]]:
        return {
            assignment.cluster_id: list(assignment.section_ids)
            for assignment in self.assignments
        }

    def dropped_cluster_ids(self) -> list[str]:
        return [
            assignment.cluster_id
            for assignment in self.assignments
            if not assignment.section_ids
        ]


class SectionAdapterResult(BaseModel):
    section_id: str
    brief: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_content_key(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        if "brief" in data:
            return data
        legacy_content = data.get("content")
        if isinstance(legacy_content, str):
            return {**data, "brief": legacy_content}
        return data


SectionContext = dict[str, str]


def detect_date_hint(text: str) -> str | None:
    normalized = text.strip()
    if not normalized:
        return None

    iso_match = _DATE_ISO_RE.search(normalized)
    if iso_match is not None:
        return iso_match.group(0)

    slash_match = _DATE_SLASH_RE.search(normalized)
    if slash_match is not None:
        day, month, year = slash_match.groups()
        return f"{year}-{month}-{day}"

    dash_match = _DATE_DASH_RE.search(normalized)
    if dash_match is not None:
        day, month, year = dash_match.groups()
        return f"{year}-{month}-{day}"

    month_match = _DATE_MONTH_TEXT_RE.search(normalized)
    if month_match is not None:
        return month_match.group(0)

    relative_match = _DATE_RELATIVE_RE.search(normalized)
    if relative_match is not None:
        return relative_match.group(0)

    year_match = _DATE_YEAR_IN_RE.search(normalized)
    if year_match is not None:
        return year_match.group(0)

    return None


def _token_count(text: str, *, encoding_name: str = DEFAULT_TOKEN_ENCODING) -> int:
    import tiktoken

    encoding = tiktoken.get_encoding(encoding_name)
    return len(encoding.encode(text))


def _is_heading_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if _HEADING_HASH_RE.match(stripped):
        return True
    letters = [char for char in stripped if char.isalpha()]
    if len(letters) < 4:
        return False
    upper_letters = sum(1 for char in letters if char.isupper())
    return upper_letters / len(letters) >= 0.85 and _HEADING_UPPER_RE.match(stripped)


def _has_result_value(line: str) -> bool:
    return bool(_RESULT_VALUE_RE.search(line))


def _has_ref_range(line: str) -> bool:
    return bool(_REF_RANGE_RE.search(line))


def _classify_line_kind(line: str) -> SpanKind:
    stripped = line.strip()
    if not stripped:
        return SpanKind.UNKNOWN
    if _is_heading_line(stripped):
        return SpanKind.HEADING
    if "|" in stripped and (
        _RESULT_LINE_RE.match(stripped)
        or (_has_result_value(stripped) and _has_ref_range(stripped))
    ):
        return SpanKind.RESULT_LINE
    if _has_result_value(stripped) and _has_ref_range(stripped):
        return SpanKind.RESULT_LINE
    if "|" in stripped or _COLUMN_GAP_RE.search(stripped):
        return SpanKind.TABLE_ROW
    if _has_result_value(stripped):
        return SpanKind.RESULT_LINE
    if _LABEL_LINE_RE.match(stripped):
        return SpanKind.LINE
    return SpanKind.LINE


def _is_prose_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if _is_heading_line(stripped):
        return False
    if _LABEL_LINE_RE.match(stripped):
        return False
    kind = _classify_line_kind(stripped)
    return kind not in (SpanKind.HEADING, SpanKind.RESULT_LINE, SpanKind.TABLE_ROW)


def _split_note_segments(note: str) -> list[str]:
    segments: list[str] = []
    for paragraph in re.split(r"\n\s*\n", note.strip()):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if "\n" in paragraph:
            for line in paragraph.splitlines():
                line = line.strip()
                if line:
                    segments.append(line)
            continue
        for sentence in _SENTENCE_SPLIT_RE.split(paragraph):
            sentence = sentence.strip()
            if sentence:
                segments.append(sentence)
    return segments


def _detect_is_pasted(note: str, segments: list[str]) -> bool:
    if _token_count(note) > PASTED_TOKEN_THRESHOLD:
        return True
    if len(segments) >= PASTED_LINE_THRESHOLD:
        return True
    heading_count = sum(1 for segment in segments if _is_heading_line(segment))
    return heading_count >= PASTED_HEADING_LINE_THRESHOLD


def split_doctor_items(
    note: str,
    *,
    session_id: str,
) -> tuple[list[DoctorItem], bool]:
    normalized_note = note.strip()
    if not normalized_note:
        return [], False

    segments = _split_note_segments(normalized_note)
    if not segments:
        return [], False

    items = [
        DoctorItem(id=f"m{index}", text=segment)
        for index, segment in enumerate(segments, start=1)
    ]
    is_pasted = _detect_is_pasted(normalized_note, segments)
    if is_pasted:
        _ = session_id
    return items, is_pasted


def doctor_items_to_spans(
    items: list[DoctorItem],
    content_ids: list[str],
) -> list[Span]:
    allowed_ids = set(content_ids)
    spans: list[Span] = []
    span_index = 0
    for item in items:
        if item.id not in allowed_ids:
            continue
        span_index += 1
        spans.append(
            Span(
                id=str(span_index),
                doc="nota_medico",
                kind=SpanKind.LINE,
                text=item.text,
                date_hint=detect_date_hint(item.text),
            )
        )
    return spans


def _next_span_id(index: int) -> str:
    return str(index)


def _append_line_span(
    spans: list[Span],
    *,
    doc: str,
    span_index: int,
    kind: SpanKind,
    text: str,
) -> int:
    spans.append(
        Span(
            id=_next_span_id(span_index),
            doc=doc,
            kind=kind,
            text=text,
            date_hint=detect_date_hint(text),
        )
    )
    return span_index + 1


def _emit_multiline_block_spans(
    spans: list[Span],
    *,
    doc: str,
    lines: list[str],
    span_index: int,
) -> int:
    prose_buffer: list[str] = []
    for line in lines:
        if _is_prose_line(line):
            prose_buffer.append(line)
            continue
        if prose_buffer:
            span_index = _append_line_span(
                spans,
                doc=doc,
                span_index=span_index,
                kind=SpanKind.PARAGRAPH,
                text="\n".join(prose_buffer),
            )
            prose_buffer = []
        kind = _classify_line_kind(line)
        span_index = _append_line_span(
            spans,
            doc=doc,
            span_index=span_index,
            kind=kind,
            text=line,
        )
    if prose_buffer:
        span_index = _append_line_span(
            spans,
            doc=doc,
            span_index=span_index,
            kind=SpanKind.PARAGRAPH,
            text="\n".join(prose_buffer),
        )
    return span_index


def build_spans_from_text(
    text: str,
    *,
    doc: str,
    session_id: str,
) -> list[Span]:
    _ = session_id
    normalized = text.strip()
    if not normalized:
        return []

    spans: list[Span] = []
    span_index = 0
    blocks = re.split(r"\n\s*\n", normalized)
    for block in blocks:
        block = block.strip()
        if not block:
            continue

        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue

        if len(lines) == 1:
            line = lines[0]
            kind = _classify_line_kind(line)
            span_index = _append_line_span(
                spans,
                doc=doc,
                span_index=span_index + 1,
                kind=kind,
                text=line,
            )
            continue

        span_index = _emit_multiline_block_spans(
            spans,
            doc=doc,
            lines=lines,
            span_index=span_index + 1,
        )
    return spans


def _split_words_into_columns(
    words: list[dict[str, object]],
    *,
    column_gap: float,
) -> list[str]:
    """Split a visual line's words into columns where the x-gap exceeds the threshold.

    pdfplumber glues multi-column rows (label / value / reference range) into a
    single text line; the x-coordinate gap between columns is far larger than the
    gap between words, so we re-split on it.
    """
    if not words:
        return []
    groups: list[list[dict[str, object]]] = [[words[0]]]
    for previous, word in zip(words, words[1:]):
        if float(word["x0"]) - float(previous["x1"]) > column_gap:
            groups.append([word])
        else:
            groups[-1].append(word)
    return [
        " ".join(str(word["text"]) for word in group).strip() for group in groups
    ]


def build_spans_from_pdf(
    path: Path,
    *,
    doc: str,
    session_id: str,
    column_gap: float = PDF_COLUMN_GAP,
) -> list[Span]:
    """Build spans from a PDF using line/word geometry.

    A flattened ``extract_text`` round-trip collapses pipe-less, blank-line-less
    lab PDFs into a single paragraph and glues multi-column rows together. Instead
    we read one span per visual line (via geometry) and split columns by x-gap,
    flagging the split spans with ``merged_columns`` for downstream review.
    """
    from context_pipeline.spans.pdf_text import pdf_to_lines

    _ = session_id
    spans: list[Span] = []
    span_index = 0
    for line in pdf_to_lines(path):
        words = line.get("words") or []
        columns = _split_words_into_columns(words, column_gap=column_gap)
        if not columns:
            fallback = str(line.get("text", "")).strip()
            columns = [fallback] if fallback else []
        merged = len(columns) > 1
        for column_text in columns:
            column_text = column_text.strip()
            if not column_text:
                continue
            span_index += 1
            spans.append(
                Span(
                    id=_next_span_id(span_index),
                    doc=doc,
                    kind=_classify_line_kind(column_text),
                    text=column_text,
                    flags=["merged_columns"] if merged else [],
                    date_hint=detect_date_hint(column_text),
                )
            )
    return spans


def merge_spans(*span_lists: list[Span]) -> list[Span]:
    merged: list[Span] = []
    next_id = 1
    for spans in span_lists:
        for span in spans:
            merged.append(span.model_copy(update={"id": str(next_id)}))
            next_id += 1
    return merged


def build_adapter_jobs(
    classify_result: ClassifyClustersResult,
    allowed_section_ids: set[str],
) -> dict[str, list[str]]:
    jobs: dict[str, list[str]] = {section_id: [] for section_id in allowed_section_ids}
    seen_per_section: dict[str, set[str]] = {
        section_id: set() for section_id in allowed_section_ids
    }

    for assignment in classify_result.assignments:
        if not assignment.section_ids:
            continue
        cluster_id = assignment.cluster_id
        for section_id in assignment.section_ids:
            if section_id not in allowed_section_ids:
                raise ValueError(f"context_unknown_section_id: {section_id!r}")
            if cluster_id in seen_per_section[section_id]:
                continue
            jobs[section_id].append(cluster_id)
            seen_per_section[section_id].add(cluster_id)

    return {
        section_id: cluster_ids
        for section_id, cluster_ids in jobs.items()
        if cluster_ids
    }


def span_to_payload_item(span: Span) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": span.id,
        "doc": span.doc,
        "kind": span.kind.value,
        "text": span.text,
    }
    if span.flags:
        payload["flags"] = list(span.flags)
    return payload


def cluster_to_payload_item(cluster: SpanCluster) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": cluster.id,
        "span_ids": list(cluster.span_ids),
    }
    if cluster.title is not None:
        payload["title"] = cluster.title
    if cluster.date_hints:
        payload["date_hints"] = list(cluster.date_hints)
    return payload


def propagate_cluster_date_hints(
    clusters: list[SpanCluster],
    spans: list[Span],
) -> list[SpanCluster]:
    spans_by_id = {span.id: span for span in spans}
    enriched: list[SpanCluster] = []
    for cluster in clusters:
        date_hints: list[str] = []
        seen_hints: set[str] = set()
        for span_id in cluster.span_ids:
            span = spans_by_id.get(span_id)
            if span is None or span.date_hint is None:
                continue
            if span.date_hint in seen_hints:
                continue
            seen_hints.add(span.date_hint)
            date_hints.append(span.date_hint)
        enriched.append(cluster.model_copy(update={"date_hints": date_hints}))
    return enriched


def apply_span_drops(spans: list[Span], drop_ids: list[str]) -> list[Span]:
    drop_set = set(drop_ids)
    return [span for span in spans if span.id not in drop_set]


def audit_triage_result(
    items: list[DoctorItem],
    result: TriageResult,
) -> None:
    item_ids = {item.id for item in items}
    referenced_ids = set(result.content_ids) | set(result.drop_ids)

    for item_id in referenced_ids:
        if item_id not in item_ids:
            raise ValueError(f"context_triage_unknown_item_id: {item_id!r}")

    overlap = set(result.content_ids) & set(result.drop_ids)
    if overlap:
        raise ValueError(
            f"context_triage_id_in_content_and_drop: {sorted(overlap)[0]!r}"
        )

    seen_content: set[str] = set()
    for item_id in result.content_ids:
        if item_id in seen_content:
            raise ValueError(f"context_triage_duplicate_content_id: {item_id!r}")
        seen_content.add(item_id)

    seen_drop: set[str] = set()
    for item_id in result.drop_ids:
        if item_id in seen_drop:
            raise ValueError(f"context_triage_duplicate_drop_id: {item_id!r}")
        seen_drop.add(item_id)


def audit_filter_spans_result(
    spans: list[Span],
    result: FilterSpansResult,
) -> None:
    span_ids = {span.id for span in spans}
    seen_drop: set[str] = set()
    for span_id in result.drop_ids:
        if span_id not in span_ids:
            raise ValueError(f"context_filter_unknown_span_id: {span_id!r}")
        if span_id in seen_drop:
            raise ValueError(f"context_filter_duplicate_drop_id: {span_id!r}")
        seen_drop.add(span_id)


def audit_span_clusters(
    spans: list[Span],
    clusters: list[SpanCluster],
    *,
    require_complete_span_coverage: bool = False,
    require_titles: bool = False,
) -> None:
    span_ids = {span.id for span in spans}
    seen_cluster_ids: set[str] = set()
    assigned_span_ids: set[str] = set()

    for cluster in clusters:
        if cluster.id in seen_cluster_ids:
            raise ValueError(f"context_cluster_duplicate_id: {cluster.id!r}")
        seen_cluster_ids.add(cluster.id)

        if require_titles and not (cluster.title and cluster.title.strip()):
            raise ValueError(f"context_cluster_missing_title: {cluster.id!r}")

        seen_span_in_cluster: set[str] = set()
        for span_id in cluster.span_ids:
            if span_id not in span_ids:
                raise ValueError(f"context_cluster_unknown_span_id: {span_id!r}")
            if span_id in seen_span_in_cluster:
                raise ValueError(
                    f"context_cluster_duplicate_span_id: {cluster.id}:{span_id!r}"
                )
            if span_id in assigned_span_ids:
                raise ValueError(
                    f"context_cluster_duplicate_span_across_clusters: {span_id!r}"
                )
            seen_span_in_cluster.add(span_id)
            assigned_span_ids.add(span_id)

    if require_complete_span_coverage:
        missing_span_ids = span_ids - assigned_span_ids
        if missing_span_ids:
            raise ValueError(
                f"context_cluster_missing_span_ids: {sorted(missing_span_ids)!r}"
            )


def audit_classify_clusters(
    clusters: list[SpanCluster],
    template: ClinicalTemplate,
    result: ClassifyClustersResult,
    *,
    require_complete_cluster_coverage: bool = False,
) -> None:
    cluster_ids = {cluster.id for cluster in clusters}
    allowed_section_ids = template.section_id_set()
    seen_cluster_ids: set[str] = set()

    for assignment in result.assignments:
        cluster_id = assignment.cluster_id
        if cluster_id not in cluster_ids:
            raise ValueError(f"context_classify_unknown_cluster_id: {cluster_id!r}")
        if cluster_id in seen_cluster_ids:
            raise ValueError(
                f"context_classify_duplicate_cluster_id: {cluster_id!r}"
            )
        seen_cluster_ids.add(cluster_id)

        seen_sections: set[str] = set()
        for section_id in assignment.section_ids:
            if section_id not in allowed_section_ids:
                raise ValueError(f"context_classify_unknown_section_id: {section_id!r}")
            if section_id in seen_sections:
                raise ValueError(
                    "context_classify_duplicate_section_id: "
                    f"{cluster_id}:{section_id!r}"
                )
            seen_sections.add(section_id)

    if require_complete_cluster_coverage:
        missing_cluster_ids = sorted(cluster_ids - seen_cluster_ids)
        if missing_cluster_ids:
            raise ValueError(
                "context_classify_missing_cluster_ids: "
                f"{missing_cluster_ids!r}"
            )
        extra_cluster_ids = sorted(seen_cluster_ids - cluster_ids)
        if extra_cluster_ids:
            raise ValueError(
                "context_classify_extra_cluster_ids: "
                f"{extra_cluster_ids!r}"
            )


def audit_section_adapter_result(
    expected_section_id: str,
    result: SectionAdapterResult,
) -> None:
    if result.section_id != expected_section_id:
        raise ValueError(
            "context_adapter_section_id_mismatch: "
            f"expected {expected_section_id!r}, got {result.section_id!r}"
        )


__all__ = [
    "DEFAULT_TOKEN_ENCODING",
    "PASTED_HEADING_LINE_THRESHOLD",
    "PASTED_LINE_THRESHOLD",
    "PASTED_TOKEN_THRESHOLD",
    "ClusterClassifyAssignment",
    "ClassifyClustersResult",
    "Directive",
    "DirectiveAction",
    "DoctorItem",
    "FilterSpansResult",
    "SectionAdapterResult",
    "SectionContext",
    "Span",
    "SpanCluster",
    "SpanKind",
    "TriageResult",
    "apply_span_drops",
    "audit_classify_clusters",
    "audit_filter_spans_result",
    "audit_section_adapter_result",
    "audit_span_clusters",
    "audit_triage_result",
    "build_adapter_jobs",
    "build_spans_from_pdf",
    "build_spans_from_text",
    "cluster_to_payload_item",
    "detect_date_hint",
    "doctor_items_to_spans",
    "merge_spans",
    "propagate_cluster_date_hints",
    "span_to_payload_item",
    "split_doctor_items",
]
