from __future__ import annotations

import re

CONTEXT_BRIEF_EVIDENCE_ID = "c1"

MARKER_PATTERN = re.compile(r"\{\{e:([^}]+)\}\}")

_FENCE_RE = re.compile(r"^```(?:\w+)?\s*|\s*```$", re.MULTILINE)


def extract_marker_id_sets(text: str) -> list[set[str]]:
    id_sets: list[set[str]] = []
    for match in MARKER_PATTERN.finditer(text):
        raw_ids = match.group(1)
        ids = {item.strip() for item in raw_ids.split(",") if item.strip()}
        if ids:
            id_sets.append(ids)
    return id_sets


def extract_all_marker_ids(text: str) -> set[str]:
    cited: set[str] = set()
    for id_set in extract_marker_id_sets(text):
        cited.update(id_set)
    return cited


def audit_evidence_markers(text: str, allowed_ids: set[str]) -> None:
    cited = extract_all_marker_ids(text)
    unknown = sorted(cited - allowed_ids)
    if unknown:
        raise ValueError(
            f"generation_unknown_evidence_marker_ids: {unknown!r}"
        )


def strip_code_fences(raw: str) -> str:
    return _FENCE_RE.sub("", raw).strip()


def strip_evidence_markers(text: str) -> str:
    return MARKER_PATTERN.sub("", text)


def parse_linked_plaintext(raw: str) -> str:
    normalized = strip_code_fences(raw.strip())
    if not normalized:
        return ""
    return normalized


__all__ = [
    "CONTEXT_BRIEF_EVIDENCE_ID",
    "MARKER_PATTERN",
    "audit_evidence_markers",
    "extract_all_marker_ids",
    "extract_marker_id_sets",
    "parse_linked_plaintext",
    "strip_code_fences",
    "strip_evidence_markers",
]
