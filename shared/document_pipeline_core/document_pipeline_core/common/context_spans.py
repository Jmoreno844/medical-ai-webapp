from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator

from document_pipeline_core.common.templates import ClinicalTemplate

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
_RESULT_MODIFIER_RE = re.compile(
    r"\b(?:ALTO|BAJO|HIGH|LOW|POSITIVO|NEGATIVO|REACTIVO|NO\s+REACTIVO)\b",
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
GENERIC_LAB_COLUMN_HEADERS = frozenset(
    {
        "resultado",
        "resultados",
        "unidad",
        "unidades",
        "referencia",
        "valor de referencia",
        "valores de referencia",
        "vr",
    }
)


class DirectiveScope(StrEnum):
    DOCUMENT = "document"
    TRANSCRIPT = "transcript"
    GENERATION = "generation"


DOCUMENT_DIRECTIVE_ACTIONS = frozenset(
    {
        "use_source",
        "ignore_source",
        "limit_source_to",
        "exclude_topic",
        "prefer_topic",
    }
)
TRANSCRIPT_DIRECTIVE_ACTIONS = frozenset(
    {
        "exclude_topic",
        "prefer_topic",
        "limit_to_topic",
    }
)
GENERATION_DIRECTIVE_ACTIONS = frozenset({"apply_instruction"})
DOCUMENT_FILTER_DIRECTIVE_ACTIONS = frozenset(
    {"ignore_source", "limit_source_to", "exclude_topic"}
)
DOCUMENT_PREFERENCE_DIRECTIVE_ACTIONS = frozenset({"use_source", "prefer_topic"})


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
    scope: DirectiveScope
    action: str
    target: str | None = None
    topic: str | None = None
    section_id: str | None = None
    instruction: str | None = None

    @model_validator(mode="after")
    def validate_directive_contract(self) -> Directive:
        action = self.action.strip()
        if not action:
            raise ValueError("context_directive_action_required")

        if self.scope == DirectiveScope.DOCUMENT:
            if action not in DOCUMENT_DIRECTIVE_ACTIONS:
                raise ValueError(
                    f"context_directive_invalid_document_action: {action!r}"
                )
            if action in DOCUMENT_FILTER_DIRECTIVE_ACTIONS | {"use_source"}:
                if not (self.target and self.target.strip()):
                    raise ValueError(
                        f"context_directive_document_target_required: {action!r}"
                    )
            if action in {"limit_source_to", "exclude_topic", "prefer_topic"}:
                if not (self.topic and self.topic.strip()):
                    raise ValueError(
                        f"context_directive_document_topic_required: {action!r}"
                    )
            return self

        if self.scope == DirectiveScope.TRANSCRIPT:
            if action == "ignore_source":
                raise ValueError(
                    "context_directive_transcript_ignore_source_prohibited"
                )
            if action not in TRANSCRIPT_DIRECTIVE_ACTIONS:
                raise ValueError(
                    f"context_directive_invalid_transcript_action: {action!r}"
                )
            if action == "limit_to_topic" and not (
                self.section_id and self.section_id.strip()
            ):
                raise ValueError(
                    "context_directive_transcript_limit_to_topic_requires_section_id"
                )
            if action in TRANSCRIPT_DIRECTIVE_ACTIONS and not (
                self.topic and self.topic.strip()
            ):
                raise ValueError(
                    f"context_directive_transcript_topic_required: {action!r}"
                )
            return self

        if self.scope == DirectiveScope.GENERATION:
            if action not in GENERATION_DIRECTIVE_ACTIONS:
                raise ValueError(
                    f"context_directive_invalid_generation_action: {action!r}"
                )
            if not (self.instruction and self.instruction.strip()):
                raise ValueError("context_directive_generation_instruction_required")
            return self

        raise ValueError(f"context_directive_unknown_scope: {self.scope!r}")


class AmbiguousDirective(BaseModel):
    directive: Directive
    reason: str


class SpanSelectorResult(BaseModel):
    keep_ids: list[str] = Field(default_factory=list)


class TriageResult(BaseModel):
    directives: list[Directive] = Field(default_factory=list)
    content_ids: list[str] = Field(default_factory=list)
    drop_ids: list[str] = Field(default_factory=list)

    @field_validator("content_ids", "drop_ids", mode="before")
    @classmethod
    def _coerce_item_ids(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        return [str(item_id) for item_id in value]


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
SectionEvidenceSpan = dict[str, object]
SectionEvidence = dict[str, list[SectionEvidenceSpan]]


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
    if _RESULT_VALUE_RE.search(line):
        return True
    normalized = _RESULT_MODIFIER_RE.sub(" ", line)
    return bool(_RESULT_VALUE_RE.search(normalized))


def _has_ref_range(line: str) -> bool:
    return bool(_REF_RANGE_RE.search(line))


def _classify_line_kind(line: str) -> SpanKind:
    stripped = line.strip()
    if not stripped:
        return SpanKind.UNKNOWN
    if "|" in stripped and (
        _RESULT_LINE_RE.match(stripped)
        or (_has_result_value(stripped) and _has_ref_range(stripped))
    ):
        return SpanKind.RESULT_LINE
    if _has_result_value(stripped) and _has_ref_range(stripped):
        return SpanKind.RESULT_LINE
    if _has_result_value(stripped):
        return SpanKind.RESULT_LINE
    if _is_heading_line(stripped):
        return SpanKind.HEADING
    if "|" in stripped or _COLUMN_GAP_RE.search(stripped):
        return SpanKind.TABLE_ROW
    if _LABEL_LINE_RE.match(stripped):
        return SpanKind.LINE
    return SpanKind.LINE


def _normalize_lab_column_header(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower()).strip(" .:-")


def _looks_like_lab_label_column(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if len(stripped) > 60:
        return False
    normalized = _normalize_lab_column_header(stripped)
    if normalized in GENERIC_LAB_COLUMN_HEADERS:
        return False
    if stripped.endswith(":"):
        return False
    if _has_result_value(stripped) or _has_ref_range(stripped):
        return False
    return bool(re.search(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]", stripped))


def _looks_like_lab_measurement_columns(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    return _has_result_value(stripped)


def _merge_lab_row_columns(columns: list[str]) -> str | None:
    if len(columns) < 2 or len(columns) > 3:
        return None
    label = columns[0].strip()
    tail = " ".join(column.strip() for column in columns[1:] if column.strip())
    if not _looks_like_lab_label_column(label):
        return None
    if not _looks_like_lab_measurement_columns(tail):
        return None
    return f"{label} {tail}".strip()


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
        DoctorItem(id=str(index), text=segment)
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
    from document_pipeline_core.context_pipeline.spans.pdf_text import pdf_to_lines

    _ = session_id
    spans: list[Span] = []
    span_index = 0
    for line in pdf_to_lines(path):
        words = line.get("words") or []
        columns = _split_words_into_columns(words, column_gap=column_gap)
        if not columns:
            fallback = str(line.get("text", "")).strip()
            columns = [fallback] if fallback else []
        merged_text = _merge_lab_row_columns(columns)
        if merged_text is not None:
            span_index += 1
            spans.append(
                Span(
                    id=_next_span_id(span_index),
                    doc=doc,
                    kind=SpanKind.RESULT_LINE,
                    text=merged_text,
                    flags=["merged_columns"],
                    date_hint=detect_date_hint(merged_text),
                )
            )
            continue
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


def build_section_evidence(
    adapter_jobs: dict[str, list[str]],
    clusters_by_id: dict[str, SpanCluster],
    spans_by_id: dict[str, Span],
) -> SectionEvidence:
    evidence: SectionEvidence = {}
    for section_id, cluster_ids in adapter_jobs.items():
        span_ids: list[str] = []
        for cluster_id in cluster_ids:
            cluster = clusters_by_id.get(cluster_id)
            if cluster is None:
                continue
            for span_id in cluster.span_ids:
                if span_id not in span_ids:
                    span_ids.append(span_id)
        spans = [spans_by_id[span_id] for span_id in span_ids if span_id in spans_by_id]
        if spans:
            evidence[section_id] = [
                {
                    "id": span.id,
                    "doc": span.doc,
                    "text": span.text,
                    **({"date_hint": span.date_hint} if span.date_hint else {}),
                }
                for span in spans
            ]
    return evidence


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


def span_to_evidence_payload_item(span: Span) -> SectionEvidenceSpan:
    payload: SectionEvidenceSpan = {
        "id": span.id,
        "doc": span.doc,
        "text": span.text,
    }
    if span.date_hint:
        payload["date_hint"] = span.date_hint
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


def resolve_document_target(
    target: str | None,
    available_documents: list[str],
) -> str | None:
    if target is None or not target.strip():
        return None
    normalized = target.strip().lower()
    if normalized in {"documentos", "documents", "all"}:
        return "__all__"
    for document_id in available_documents:
        if document_id.lower() == normalized:
            return document_id
    for document_id in available_documents:
        document_lower = document_id.lower()
        if normalized in document_lower or document_lower in normalized:
            return document_id
    return None


def directives_for_scope(
    directives: list[Directive],
    scope: DirectiveScope,
) -> list[Directive]:
    return [directive for directive in directives if directive.scope == scope]


def document_filter_directives(directives: list[Directive]) -> list[Directive]:
    return [
        directive
        for directive in directives_for_scope(directives, DirectiveScope.DOCUMENT)
        if directive.action in DOCUMENT_FILTER_DIRECTIVE_ACTIONS
    ]


def document_preference_directives(directives: list[Directive]) -> list[Directive]:
    return [
        directive
        for directive in directives_for_scope(directives, DirectiveScope.DOCUMENT)
        if directive.action in DOCUMENT_PREFERENCE_DIRECTIVE_ACTIONS
    ]


def transcript_directives(directives: list[Directive]) -> list[Directive]:
    return directives_for_scope(directives, DirectiveScope.TRANSCRIPT)


def transcript_directives_for_section(
    directives: list[Directive],
    section_id: str,
) -> list[Directive]:
    scoped: list[Directive] = []
    for directive in transcript_directives(directives):
        directive_section_id = directive.section_id
        if directive_section_id and directive_section_id.strip():
            if directive_section_id.strip() == section_id:
                scoped.append(directive)
            continue
        scoped.append(directive)
    return scoped


def audit_directives(
    directives: list[Directive],
    *,
    available_documents: list[str] | None = None,
    template_section_ids: list[str] | None = None,
) -> None:
    allowed_documents = set(available_documents or [])
    allowed_sections = set(template_section_ids or [])
    for directive in directives:
        if directive.scope == DirectiveScope.DOCUMENT and allowed_documents:
            if directive.action in DOCUMENT_FILTER_DIRECTIVE_ACTIONS | {"use_source"}:
                resolved = resolve_document_target(
                    directive.target,
                    list(allowed_documents),
                )
                if resolved is None:
                    continue
                if resolved != "__all__" and resolved not in allowed_documents:
                    raise ValueError(
                        "context_directive_unknown_document_target: "
                        f"{directive.target!r}"
                    )
        if directive.section_id and allowed_sections:
            if directive.section_id not in allowed_sections:
                raise ValueError(
                    f"context_directive_unknown_section_id: {directive.section_id!r}"
                )


def audit_span_selector_result(
    spans: list[Span],
    result: SpanSelectorResult,
) -> None:
    span_ids = {span.id for span in spans}
    seen_keep: set[str] = set()
    for span_id in result.keep_ids:
        if span_id not in span_ids:
            raise ValueError(f"context_span_selector_unknown_span_id: {span_id!r}")
        if span_id in seen_keep:
            raise ValueError(f"context_span_selector_duplicate_keep_id: {span_id!r}")
        seen_keep.add(span_id)


def audit_triage_result(
    items: list[DoctorItem],
    result: TriageResult,
    *,
    available_documents: list[str] | None = None,
    template_section_ids: list[str] | None = None,
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

    audit_directives(
        result.directives,
        available_documents=available_documents,
        template_section_ids=template_section_ids,
    )


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
    "AmbiguousDirective",
    "ClusterClassifyAssignment",
    "ClassifyClustersResult",
    "DOCUMENT_DIRECTIVE_ACTIONS",
    "DOCUMENT_FILTER_DIRECTIVE_ACTIONS",
    "DOCUMENT_PREFERENCE_DIRECTIVE_ACTIONS",
    "Directive",
    "DirectiveScope",
    "DoctorItem",
    "FilterSpansResult",
    "GENERATION_DIRECTIVE_ACTIONS",
    "SectionAdapterResult",
    "SectionContext",
    "SectionEvidence",
    "SectionEvidenceSpan",
    "Span",
    "SpanCluster",
    "SpanKind",
    "SpanSelectorResult",
    "TRANSCRIPT_DIRECTIVE_ACTIONS",
    "TriageResult",
    "apply_span_drops",
    "audit_classify_clusters",
    "audit_directives",
    "audit_filter_spans_result",
    "audit_section_adapter_result",
    "audit_span_clusters",
    "audit_span_selector_result",
    "audit_triage_result",
    "build_adapter_jobs",
    "build_section_evidence",
    "build_spans_from_pdf",
    "build_spans_from_text",
    "cluster_to_payload_item",
    "detect_date_hint",
    "directives_for_scope",
    "document_filter_directives",
    "document_preference_directives",
    "doctor_items_to_spans",
    "merge_spans",
    "propagate_cluster_date_hints",
    "resolve_document_target",
    "span_to_payload_item",
    "split_doctor_items",
    "transcript_directives",
    "transcript_directives_for_section",
]
