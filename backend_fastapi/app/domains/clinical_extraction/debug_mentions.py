from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from app.domains.clinical_extraction.schemas import (
    ClinicalExtractionChunk,
    DebugClinicalMentionEvidenceResult,
)
from app.domains.clinical_extraction.validator import normalize_text

REQUIRED_CORRECTION_ATTRIBUTE_KINDS = {
    "prior_value",
    "replacement_value",
    "repair_language",
}


@dataclass
class _QuoteMatch:
    matched: bool
    match_score: float | None = None
    matched_chunk_ids: list[str] | None = None
    uttered_by_role: str | None = None
    ambiguous: bool = False


def process_debug_clinical_mentions(
    raw_mentions: dict[str, Any],
    chunks: list[ClinicalExtractionChunk],
    *,
    latency_ms: int | None = None,
) -> tuple[dict[str, Any], list[DebugClinicalMentionEvidenceResult], dict[str, Any]]:
    processed = _normalize_root(raw_mentions)
    evidence_results: list[DebugClinicalMentionEvidenceResult] = []
    stats: dict[str, Any] = {
        "mentions_emitted": 0,
        "mentions_dropped_unmatched": 0,
        "mentions_dropped_ambiguous": 0,
        "attributes_dropped_ungrounded": 0,
        "correction_mentions_rejected": 0,
        "quotes_unmatched": 0,
        "quotes_ambiguous": 0,
        "ground_strict_forced_null": 0,
        "duplicate_mentions_removed": 0,
        "latency_ms": latency_ms,
        "validation_warnings": [],
    }

    processed_mentions: list[dict[str, Any]] = []
    for index, item in enumerate(processed["mentions"]):
        if not isinstance(item, dict):
            continue
        fact_path = f"mentions[{index}]"
        mention = deepcopy(item)
        matches, had_ambiguous = _collect_evidence(
            mention.get("evidence"),
            fact_path,
            chunks,
            evidence_results,
            stats,
        )
        if not matches:
            if had_ambiguous:
                stats["mentions_dropped_ambiguous"] += 1
            else:
                stats["mentions_dropped_unmatched"] += 1
            continue
        if not _mention_fields_grounded(mention, matches, fact_path, stats):
            stats["mentions_dropped_unmatched"] += 1
            continue
        mention["attributes"] = _ground_attributes(
            mention.get("attributes"),
            matches,
            fact_path,
            stats,
        )
        if mention.get("speech_act") == "correction" and not _has_required_correction_attributes(
            mention["attributes"]
        ):
            stats["correction_mentions_rejected"] += 1
            _warn(stats, f"{fact_path}: correction_missing_required_attributes")
            continue
        mention["evidence"] = _filtered_evidence(mention.get("evidence"), matches)
        processed_mentions.append(mention)

    processed["mentions"] = _remove_duplicates(processed_mentions, stats)
    stats["mentions_emitted"] = len(processed["mentions"])
    return processed, evidence_results, stats


def _normalize_root(raw_mentions: dict[str, Any]) -> dict[str, Any]:
    mentions = raw_mentions.get("mentions") if isinstance(raw_mentions, dict) else None
    return {"mentions": mentions if isinstance(mentions, list) else []}


def _had_any_evidence(mention: dict[str, Any]) -> bool:
    evidence = mention.get("evidence")
    return isinstance(evidence, list) and bool(evidence)


def _mention_fields_grounded(
    mention: dict[str, Any],
    matches: list[DebugClinicalMentionEvidenceResult],
    fact_path: str,
    stats: dict[str, Any],
) -> bool:
    for field in ("entity_raw", "proposition_raw"):
        value = str(mention.get(field) or "")
        if _value_appears_in_matches(value, matches):
            continue
        stats["ground_strict_forced_null"] += 1
        _warn(stats, f"{fact_path}.{field}: ungrounded")
        return False
    return True


def _ground_attributes(
    attributes: Any,
    matches: list[DebugClinicalMentionEvidenceResult],
    fact_path: str,
    stats: dict[str, Any],
) -> list[dict[str, Any]]:
    grounded: list[dict[str, Any]] = []
    for index, item in enumerate(attributes if isinstance(attributes, list) else []):
        if not isinstance(item, dict):
            continue
        raw_text = str(item.get("raw_text") or "")
        kind = str(item.get("kind") or "")
        if not raw_text or not kind or not _value_appears_in_matches(raw_text, matches):
            stats["attributes_dropped_ungrounded"] += 1
            _warn(stats, f"{fact_path}.attributes[{index}]: ungrounded")
            continue
        grounded.append({"kind": kind, "raw_text": raw_text})
    return grounded


def _has_required_correction_attributes(attributes: list[dict[str, Any]]) -> bool:
    kinds = {str(item.get("kind") or "") for item in attributes}
    return REQUIRED_CORRECTION_ATTRIBUTE_KINDS.issubset(kinds)


def _filtered_evidence(
    evidence: Any,
    matches: list[DebugClinicalMentionEvidenceResult],
) -> list[dict[str, Any]]:
    valid_keys = {(item.quote, item.turn_id) for item in matches}
    filtered: list[dict[str, Any]] = []
    for item in evidence if isinstance(evidence, list) else []:
        if not isinstance(item, dict):
            continue
        quote = str(item.get("quote") or "")
        turn_id = str(item.get("turn_id")) if item.get("turn_id") else None
        if (quote, turn_id) in valid_keys:
            filtered.append({"quote": quote, "turn_id": turn_id})
    return filtered


def _collect_evidence(
    evidence: Any,
    fact_path: str,
    chunks: list[ClinicalExtractionChunk],
    evidence_results: list[DebugClinicalMentionEvidenceResult],
    stats: dict[str, Any],
) -> tuple[list[DebugClinicalMentionEvidenceResult], bool]:
    valid_matches: list[DebugClinicalMentionEvidenceResult] = []
    had_ambiguous = False
    for evidence_index, item in enumerate(evidence if isinstance(evidence, list) else []):
        if not isinstance(item, dict):
            continue
        quote = str(item.get("quote") or "")
        turn_id = str(item.get("turn_id")) if item.get("turn_id") else None
        match = _match_quote_to_chunks(quote, chunks, turn_id=turn_id)
        result = DebugClinicalMentionEvidenceResult(
            fact_path=fact_path,
            quote=quote,
            turn_id=turn_id,
            matched=match.matched,
            match_score=match.match_score,
            matched_chunk_ids=match.matched_chunk_ids or [],
            uttered_by_role=match.uttered_by_role,
            ambiguous=match.ambiguous,
            speaker_mismatch=False,
        )
        evidence_results.append(result)
        if not result.matched:
            stats["quotes_unmatched"] += 1
            _warn(stats, f"{fact_path}.evidence[{evidence_index}]: quote_unmatched")
            continue
        if result.ambiguous:
            stats["quotes_ambiguous"] += 1
            had_ambiguous = True
            _warn(stats, f"{fact_path}.evidence[{evidence_index}]: quote_ambiguous")
            continue
        valid_matches.append(result)
    return valid_matches, had_ambiguous


def _value_appears_in_matches(
    value: str,
    matches: list[DebugClinicalMentionEvidenceResult],
) -> bool:
    normalized_value = normalize_text(value)
    if not normalized_value:
        return False
    return any(normalized_value in normalize_text(match.quote) for match in matches)


def _remove_duplicates(
    mentions: list[dict[str, Any]],
    stats: dict[str, Any],
) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for mention in mentions:
        quote = ""
        evidence = mention.get("evidence")
        if isinstance(evidence, list) and evidence:
            first = evidence[0]
            if isinstance(first, dict):
                quote = str(first.get("quote") or "")
        key = "|".join(
            [
                str(mention.get("entity_type") or ""),
                str(mention.get("speech_act") or ""),
                normalize_text(str(mention.get("entity_raw") or "")),
                normalize_text(str(mention.get("proposition_raw") or "")),
                normalize_text(quote),
            ]
        )
        if key in seen:
            stats["duplicate_mentions_removed"] += 1
            continue
        seen.add(key)
        unique.append(mention)
    return unique


def _match_quote_to_chunks(
    quote: str,
    chunks: list[ClinicalExtractionChunk],
    *,
    turn_id: str | None,
) -> _QuoteMatch:
    normalized_quote = normalize_text(quote)
    if not normalized_quote:
        return _QuoteMatch(matched=False)
    candidates = _single_turn_candidates(chunks, normalized_quote, turn_id)
    if not _has_viable_candidate(candidates):
        candidates.extend(_adjacent_window_candidates(chunks, normalized_quote))
    if not candidates:
        return _QuoteMatch(matched=False)
    candidates.sort(key=lambda item: item[1], reverse=True)
    best_chunks, best_score = candidates[0]
    if best_score < 82:
        return _QuoteMatch(matched=False, match_score=best_score)
    close_matches = [
        item
        for item in candidates
        if item[1] >= best_score - 3 and len(item[0]) == len(best_chunks)
    ]
    ambiguous = len(normalized_quote.split()) < 3 or len(close_matches) > 1
    speakers = {chunk.speaker for chunk in best_chunks if chunk.speaker}
    uttered_by_role = speakers.pop() if len(speakers) == 1 else None
    return _QuoteMatch(
        matched=True,
        match_score=best_score,
        matched_chunk_ids=[chunk.chunk_id for chunk in best_chunks],
        uttered_by_role=uttered_by_role,
        ambiguous=ambiguous,
    )


def _single_turn_candidates(
    chunks: list[ClinicalExtractionChunk],
    normalized_quote: str,
    turn_id: str | None,
) -> list[tuple[list[ClinicalExtractionChunk], float]]:
    candidates: list[tuple[list[ClinicalExtractionChunk], float]] = []
    seen: set[tuple[str, ...]] = set()
    hinted = [chunk for chunk in chunks if chunk.chunk_id == turn_id]
    for chunk in hinted:
        _append_match_candidate(candidates, seen, [chunk], normalized_quote)
    for chunk in chunks:
        _append_match_candidate(candidates, seen, [chunk], normalized_quote)
    return candidates


def _adjacent_window_candidates(
    chunks: list[ClinicalExtractionChunk],
    normalized_quote: str,
) -> list[tuple[list[ClinicalExtractionChunk], float]]:
    candidates: list[tuple[list[ClinicalExtractionChunk], float]] = []
    seen: set[tuple[str, ...]] = set()
    for index in range(len(chunks) - 1):
        _append_match_candidate(
            candidates,
            seen,
            [chunks[index], chunks[index + 1]],
            normalized_quote,
        )
    return candidates


def _has_viable_candidate(
    candidates: list[tuple[list[ClinicalExtractionChunk], float]],
) -> bool:
    return any(score >= 82 for _chunks, score in candidates)


def _append_match_candidate(
    candidates: list[tuple[list[ClinicalExtractionChunk], float]],
    seen: set[tuple[str, ...]],
    candidate_chunks: list[ClinicalExtractionChunk],
    normalized_quote: str,
) -> None:
    key = tuple(chunk.chunk_id for chunk in candidate_chunks)
    if key in seen:
        return
    seen.add(key)
    candidates.append(
        (
            candidate_chunks,
            _score(
                normalized_quote,
                normalize_text(" ".join(chunk.text for chunk in candidate_chunks)),
            ),
        )
    )


def _score(quote: str, text: str) -> float:
    if not quote or not text:
        return 0.0
    if quote in text:
        return 100.0
    quote_tokens = set(quote.split())
    text_tokens = set(text.split())
    token_overlap = len(quote_tokens & text_tokens) / max(len(quote_tokens), 1)
    sequence = SequenceMatcher(None, quote, text).ratio()
    return round(max(token_overlap, sequence) * 100, 2)


def _warn(stats: dict[str, Any], warning: str) -> None:
    warnings = stats.setdefault("validation_warnings", [])
    if isinstance(warnings, list):
        warnings.append(warning)
