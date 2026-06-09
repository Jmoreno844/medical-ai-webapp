from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


ATONIC_PRONOUNS = frozenset({"me", "te", "le", "se", "nos"})

ALLERGY_DOMAIN_TERMS = frozenset({"alergia", "alergias", "alergico", "alergica"})
MEDICATION_DOMAIN_TERMS = frozenset(
    {"medicamento", "medicamentos", "medicina", "medicinas", "tomo"}
)

ITEM_NEGATION_PATTERNS = (
  re.compile(r"\balergic[oa]\s+a(?:l|la)?\s+\w"),
  re.compile(r"\balergic[oa]\s+al?\s+\w"),
  re.compile(r"\bno\s+tomo\s+\w"),
  re.compile(r"\bno\s+toma\s+\w"),
)


@dataclass
class LocalizedEvidenceRecord:
    quote: str
    supports_fields: list[str] = field(default_factory=list)
    matched: bool = False
    ambiguous: bool = False
    chunk_hint: str | None = None
    evidence_index: int = 0


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", value.lower())).strip()


def contains_negation(normalized_quote: str) -> bool:
    tokens = set(normalized_quote.split())
    return bool(tokens & {"no", "ningun", "ninguna", "niega", "sin"})


def supports_allergy_summary_domain(normalized_quote: str) -> bool:
    return any(term in normalized_quote for term in ALLERGY_DOMAIN_TERMS)


def supports_medication_summary_domain(normalized_quote: str) -> bool:
    return any(term in normalized_quote for term in MEDICATION_DOMAIN_TERMS)


def supports_summary_domain(fact_path: str, normalized_quote: str) -> bool:
    if fact_path == "allergy_summary":
        return supports_allergy_summary_domain(normalized_quote)
    if fact_path == "medication_summary":
        return supports_medication_summary_domain(normalized_quote)
    return False


def is_collection_scope_negation(fact_path: str, quote: str) -> bool:
    normalized_quote = normalize_text(quote)
    if not contains_negation(normalized_quote):
        return False
    if not supports_summary_domain(fact_path, normalized_quote):
        return False
    return not any(pattern.search(normalized_quote) for pattern in ITEM_NEGATION_PATTERNS)


def _subject_raw_text_supported(
    value: str,
    localized_evidence: list[LocalizedEvidenceRecord],
) -> tuple[bool, str]:
    normalized_value = normalize_text(value)
    if not normalized_value:
        return False, "empty_value"
    if normalized_value in ATONIC_PRONOUNS:
        return False, "atonic_pronoun"

    for record in localized_evidence:
        if "subject_raw_text" not in record.supports_fields:
            continue
        normalized_quote = normalize_text(record.quote)
        if normalized_value in normalized_quote:
            return True, ""
    return False, "subject_raw_text_not_supported"


TOP_LEVEL_FACT_SECTIONS = frozenset(
    {
        "information_sources",
        "chief_complaints",
        "clinical_events",
        "history",
        "allergies",
        "allergy_summary",
        "medications",
        "medication_summary",
        "objective_data",
        "diagnostic_studies",
        "interventions",
        "clinician_assessment",
        "care_plan",
        "data_quality",
        "custom_facts",
    }
)


SUMMARY_FACT_PATHS = frozenset({"allergy_summary", "medication_summary"})


def apply_supports_fields_validation(
    fact_path: str,
    item: dict[str, Any],
    warnings: list[str],
) -> bool:
    evidence_items = item.get("evidence")
    if not isinstance(evidence_items, list):
        return False
    allowed_fields = {key for key in item if key != "evidence"}
    emitted_warning = False
    for evidence_index, evidence in enumerate(evidence_items):
        if not isinstance(evidence, dict):
            continue
        supports_fields = [
            str(field)
            for field in evidence.get("supports_fields", [])
            if isinstance(field, str)
        ]
        valid_supports: list[str] = []
        for field in supports_fields:
            if (
                fact_path in SUMMARY_FACT_PATHS
                and field in {"assertion", "scope_raw_text"}
            ):
                if field in allowed_fields:
                    valid_supports.append(field)
                continue
            if field in TOP_LEVEL_FACT_SECTIONS:
                warnings.append(
                    f"{fact_path}.evidence[{evidence_index}].supports_fields: "
                    f"invalid_section_reference:field={field}"
                )
                emitted_warning = True
                continue
            if field in INFERRED_CLASSIFICATION_FIELDS:
                warnings.append(
                    f"{fact_path}.evidence[{evidence_index}].supports_fields: "
                    f"inferred_field_not_supported:field={field}"
                )
                emitted_warning = True
                continue
            if field not in allowed_fields:
                warnings.append(
                    f"{fact_path}.evidence[{evidence_index}].supports_fields: "
                    f"field_not_sibling:field={field}"
                )
                emitted_warning = True
                continue
            valid_supports.append(field)
        evidence["supports_fields"] = valid_supports
    return emitted_warning


INFERRED_CLASSIFICATION_FIELDS = frozenset(
    {
        "assertion",
        "claim_lifecycle",
        "subject_role",
        "information_source_role",
        "reported_certainty",
        "certainty",
        "medication_use_status",
        "allergy_clinical_status",
        "reliability_assertion",
        "lifecycle_stage",
        "result_availability",
        "decision_status",
        "execution_status",
        "original_certainty",
        "data_type",
        "event_kind",
        "setting",
        "measured_by",
        "prescribed_by",
        "stopped_by",
        "proposed_by",
        "accepted_by",
        "declined_by",
    }
)


def apply_subject_raw_text_validation(
    fact_path: str,
    item: dict[str, Any],
    localized_evidence: list[LocalizedEvidenceRecord],
    warnings: list[str],
) -> bool:
    value = item.get("subject_raw_text")
    if value in (None, ""):
        return False

    localized = [
        record
        for record in localized_evidence
        if record.matched and not record.ambiguous
    ]
    supported, reason = _subject_raw_text_supported(str(value), localized)
    if supported:
        return False

    if reason == "atonic_pronoun":
        final_reason = "atonic_pronoun"
    elif localized and normalize_text(str(value)) not in {
        normalize_text(record.quote) for record in localized
    }:
        final_reason = "not_in_localized_quote"
    else:
        final_reason = reason or "subject_raw_text_not_supported"

    item["subject_raw_text"] = None
    warnings.append(
        f"{fact_path}.subject_raw_text: subject_raw_text_not_explicit:"
        f"discarded={value}:reason={final_reason}"
    )
    return True


def _none_reported_evidence_ids(
    localized_evidence: list[LocalizedEvidenceRecord],
    all_evidence: list[LocalizedEvidenceRecord],
) -> str:
    ids = [
        record.chunk_hint or str(record.evidence_index)
        for record in (localized_evidence or all_evidence)
    ]
    return ",".join(ids) if ids else "none"


def _validate_none_reported_assertion(
    fact_path: str,
    localized_evidence: list[LocalizedEvidenceRecord],
    all_evidence: list[LocalizedEvidenceRecord],
) -> tuple[bool, str]:
    if not all_evidence:
        return False, "no_evidence"

    localized = [record for record in localized_evidence if record.matched]
    if not localized:
        return False, "quote_unmatched"

    unambiguous = [record for record in localized if not record.ambiguous]
    if not unambiguous:
        return False, "quote_ambiguous"

    assertion_supported = any(
        "assertion" in record.supports_fields for record in unambiguous
    )
    if not assertion_supported:
        return False, "assertion_not_supported"

    for record in unambiguous:
        if "assertion" not in record.supports_fields:
            continue
        normalized_quote = normalize_text(record.quote)
        if not contains_negation(normalized_quote):
            continue
        if not supports_summary_domain(fact_path, normalized_quote):
            continue
        if not is_collection_scope_negation(fact_path, record.quote):
            return False, "item_specific_negation"
        return True, ""

    return False, "missing_explicit_collection_negation"


def apply_collection_summary_validation(
    fact_path: str,
    item: dict[str, Any],
    localized_evidence: list[LocalizedEvidenceRecord],
    all_evidence: list[LocalizedEvidenceRecord],
    warnings: list[str],
) -> bool:
    if not fact_path.endswith("_summary"):
        return False
    if item.get("assertion") != "none_reported":
        return False

    valid, reason = _validate_none_reported_assertion(
        fact_path,
        localized_evidence,
        all_evidence,
    )
    if valid:
        return False

    evidence_ids = _none_reported_evidence_ids(localized_evidence, all_evidence)
    item["assertion"] = None
    item["scope_raw_text"] = None
    item["evidence"] = []
    warnings.append(
        f"{fact_path}.assertion: "
        f"collection_summary_none_reported_without_explicit_evidence:"
        f"discarded=none_reported:reason={reason}:evidence={evidence_ids}"
    )
    return True
