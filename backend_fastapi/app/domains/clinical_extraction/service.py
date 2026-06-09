from __future__ import annotations

import logging
import re
from copy import deepcopy
from datetime import datetime, timezone
from difflib import SequenceMatcher
from types import SimpleNamespace
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.core.service_jwt import issue_clinical_extraction_callback_token
from app.db.models import (
    ClinicalExtraction,
    ClinicalFactEvidence,
    Encounter,
    TranscriptionRecordingSession,
)
from app.domains.clinical_extraction.schemas import (
    ClinicalExtractionChunk,
    ClinicalExtractionEvidenceResult,
    ClinicalExtractionWorkItemResponse,
    DebugClinicalExtractionContext,
)
from app.domains.clinical_extraction.validator import (
    LocalizedEvidenceRecord,
    apply_collection_summary_validation,
    apply_subject_raw_text_validation,
    apply_supports_fields_validation,
    normalize_text,
)
from app.integrations.clinical_extraction_tasks import (
    enqueue_clinical_extraction_task,
    should_use_clinical_extraction_cloud_tasks,
)
from app.integrations.http_json import post_json_async

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "clinical_facts_v1"
STATUS_PENDING = "pending"
STATUS_EXTRACTING = "extracting"
STATUS_EXTRACTED = "extracted"
STATUS_FAILED_EXTRACTION = "failed_extraction"
STATUS_FAILED_VALIDATION = "failed_validation"
GROUND_STRICT_FIELDS = {
    "dose_value",
    "dose_unit",
    "route_raw",
    "frequency_raw",
    "value_raw",
    "unit_raw",
}
INFERRED_FIELDS = {
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
PATH_ALLOWED_FIELDS: dict[str, set[str]] = {
    "information_sources": {
        "information_source_role",
        "relationship_raw_text",
        "reliability_assertion",
        "reliability_raw_text",
        "evidence",
    },
    "medications": {
        "name_raw",
        "dose_value",
        "dose_unit",
        "route_raw",
        "frequency_raw",
        "timing_raw",
        "exposure_duration_raw",
        "prescribed_duration_raw",
        "adherence_raw",
        "medication_use_status",
        "certainty",
        "prescribed_by",
        "stopped_by",
        "subject_role",
        "subject_raw_text",
        "information_source_role",
        "evidence",
    },
    "interventions": {
        "type_raw",
        "decision_status",
        "execution_status",
        "proposed_by",
        "accepted_by",
        "declined_by",
        "reason_raw",
        "conditional_on_raw_text",
        "subject_role",
        "subject_raw_text",
        "information_source_role",
        "evidence",
    },
    "care_plan.recommendations": {
        "text_raw",
        "conditional_on_raw_text",
        "evidence",
    },
    "care_plan.education": {
        "text_raw",
        "conditional_on_raw_text",
        "evidence",
    },
    "care_plan.warning_signs": {
        "text_raw",
        "conditional_on_raw_text",
        "evidence",
    },
    "care_plan.disposition": {
        "text_raw",
        "conditional_on_raw_text",
        "evidence",
    },
    "care_plan.work_leave": {
        "text_raw",
        "conditional_on_raw_text",
        "evidence",
    },
    "care_plan.follow_up": {
        "text_raw",
        "conditional_on_raw_text",
        "evidence",
    },
}
LOCAL_CLINICAL_EXTRACTION_DISPATCH_TIMEOUT_SECONDS = 180


def build_extraction_chunks_from_transcript(
    transcript_json: dict[str, Any],
) -> list[ClinicalExtractionChunk]:
    return _build_extraction_chunks(transcript_json)


async def get_debug_transcript_session(
    db_session: AsyncSession,
    *,
    session_id: str,
) -> TranscriptionRecordingSession | None:
    result = await db_session.execute(
        select(TranscriptionRecordingSession)
        .options(
            selectinload(TranscriptionRecordingSession.encounter),
            selectinload(TranscriptionRecordingSession.encounter).selectinload(
                Encounter.patient
            ),
        )
        .where(TranscriptionRecordingSession.session_id == session_id)
    )
    recording_session = result.scalar_one_or_none()
    if not recording_session or not recording_session.transcript_json:
        return None
    return recording_session


def build_debug_recording_session_context(
    *,
    recording_session: TranscriptionRecordingSession | None = None,
    context: DebugClinicalExtractionContext | None = None,
) -> Any:
    if recording_session is not None:
        return recording_session
    ctx = context or DebugClinicalExtractionContext()
    return SimpleNamespace(
        encounter_id=ctx.encounter_id,
        document_id=ctx.document_id,
        doctor_id=ctx.doctor_id,
        encounter=SimpleNamespace(
            occurred_at=ctx.occurred_at,
            patient=SimpleNamespace(
                id=ctx.patient_id,
                name=ctx.patient_name,
            ),
        ),
    )


def apply_debug_clinical_extraction(
    raw_facts: dict[str, Any],
    chunks: list[ClinicalExtractionChunk],
    *,
    recording_session: Any,
    language: str | None = None,
    latency_ms: int | None = None,
) -> tuple[dict[str, Any], list[ClinicalExtractionEvidenceResult], dict[str, Any]]:
    return process_clinical_facts(
        raw_facts,
        chunks,
        recording_session=recording_session,
        language=language,
        latency_ms=latency_ms,
    )


async def trigger_clinical_extraction_for_session(
    db_session: AsyncSession,
    recording_session: TranscriptionRecordingSession,
    *,
    settings: Settings,
) -> None:
    if not settings.clinical_extraction_enabled:
        return
    await ensure_clinical_extraction_row(db_session, recording_session)
    await db_session.commit()
    payload = {
        "session_id": recording_session.session_id,
        "encounter_id": recording_session.encounter_id,
        "document_id": recording_session.document_id,
        "doctor_id": recording_session.doctor_id,
    }
    if should_use_clinical_extraction_cloud_tasks(settings):
        enqueue_clinical_extraction_task(payload, settings=settings)
        return
    if not settings.clinical_extraction_worker_base_url:
        logger.info(
            "Clinical extraction enabled but no local worker base URL is configured",
            extra={"session_id": recording_session.session_id},
        )
        return

    url = (
        f"{settings.clinical_extraction_worker_base_url.rstrip('/')}"
        f"{settings.api_v1_prefix}/internal/clinical-extraction/tasks/"
        f"{recording_session.session_id}"
    )
    await post_json_async(
        url,
        payload,
        timeout=LOCAL_CLINICAL_EXTRACTION_DISPATCH_TIMEOUT_SECONDS,
    )


async def ensure_clinical_extraction_row(
    db_session: AsyncSession,
    recording_session: TranscriptionRecordingSession,
) -> ClinicalExtraction:
    result = await db_session.execute(
        select(ClinicalExtraction).where(
            ClinicalExtraction.session_id == recording_session.session_id
        )
    )
    extraction = result.scalar_one_or_none()
    if extraction:
        return extraction

    extraction = ClinicalExtraction(
        session_id=recording_session.session_id,
        encounter_id=recording_session.encounter_id,
        document_id=recording_session.document_id,
        doctor_id=recording_session.doctor_id,
        schema_version=SCHEMA_VERSION,
        extraction_model=None,
        extraction_status=STATUS_PENDING,
        facts_json=None,
        raw_model_output_json=None,
        grounding_stats_json=None,
        retry_count=0,
        error_code=None,
        created_at=datetime.now(timezone.utc),
        finalized_at=None,
    )
    db_session.add(extraction)
    await db_session.flush()
    return extraction


async def get_clinical_extraction_work_item(
    db_session: AsyncSession,
    *,
    session_id: str,
    settings: Settings,
) -> ClinicalExtractionWorkItemResponse | None:
    result = await db_session.execute(
        select(TranscriptionRecordingSession)
        .options(
            selectinload(TranscriptionRecordingSession.encounter),
            selectinload(TranscriptionRecordingSession.document),
        )
        .where(TranscriptionRecordingSession.session_id == session_id)
    )
    recording_session = result.scalar_one_or_none()
    if not recording_session or not recording_session.transcript_json:
        return None

    extraction = await ensure_clinical_extraction_row(db_session, recording_session)
    extraction.extraction_status = STATUS_EXTRACTING
    extraction.retry_count = (extraction.retry_count or 0) + 1
    extraction.error_code = None
    await db_session.commit()

    callback_token = issue_clinical_extraction_callback_token(
        user_id=recording_session.doctor_id,
        session_id=recording_session.session_id,
        encounter_id=recording_session.encounter_id,
        document_id=recording_session.document_id,
        settings=settings,
    )
    return ClinicalExtractionWorkItemResponse(
        session_id=recording_session.session_id,
        encounter_id=recording_session.encounter_id,
        document_id=recording_session.document_id,
        doctor_id=recording_session.doctor_id,
        language=_transcript_language(recording_session.transcript_json),
        chunks=_build_extraction_chunks(recording_session.transcript_json),
        callback_token=callback_token,
    )


async def apply_clinical_extraction_result(
    db_session: AsyncSession,
    *,
    session_id: str,
    status: str,
    facts: dict[str, Any] | None,
    raw_model_output: dict[str, Any] | None,
    extraction_model: str | None,
    grounding_stats: dict[str, Any] | None,
    error_code: str | None,
    latency_ms: int | None,
) -> ClinicalExtraction | None:
    result = await db_session.execute(
        select(TranscriptionRecordingSession)
        .options(
            selectinload(TranscriptionRecordingSession.encounter),
            selectinload(TranscriptionRecordingSession.encounter).selectinload(
                Encounter.patient
            ),
            selectinload(TranscriptionRecordingSession.document),
            selectinload(TranscriptionRecordingSession.doctor),
        )
        .where(TranscriptionRecordingSession.session_id == session_id)
    )
    recording_session = result.scalar_one_or_none()
    if not recording_session:
        return None

    extraction = await ensure_clinical_extraction_row(db_session, recording_session)
    if extraction.extraction_status == STATUS_EXTRACTED and status == STATUS_EXTRACTED:
        return extraction

    if status != STATUS_EXTRACTED:
        extraction.extraction_status = (
            STATUS_FAILED_VALIDATION
            if status == STATUS_FAILED_VALIDATION
            else STATUS_FAILED_EXTRACTION
        )
        extraction.error_code = error_code or "clinical_extraction_failed"
        extraction.extraction_model = extraction_model
        extraction.finalized_at = datetime.now(timezone.utc)
        await db_session.commit()
        return extraction

    chunks = _build_extraction_chunks(recording_session.transcript_json or {})
    processed_facts, evidence_rows, stats = process_clinical_facts(
        facts or {},
        chunks,
        recording_session=recording_session,
        language=_transcript_language(recording_session.transcript_json or {}),
        grounding_stats=grounding_stats,
        latency_ms=latency_ms,
    )
    await db_session.execute(
        delete(ClinicalFactEvidence).where(
            ClinicalFactEvidence.extraction_id == extraction.id
        )
    )
    extraction.extraction_model = extraction_model
    extraction.extraction_status = STATUS_EXTRACTED
    extraction.facts_json = processed_facts
    extraction.raw_model_output_json = raw_model_output or facts or {}
    extraction.grounding_stats_json = stats
    extraction.error_code = None
    extraction.finalized_at = datetime.now(timezone.utc)
    await db_session.flush()

    for evidence in evidence_rows:
        db_session.add(
            ClinicalFactEvidence(
                extraction_id=extraction.id,
                fact_path=evidence.fact_path,
                quote=evidence.quote,
                supports_fields=evidence.supports_fields,
                chunk_hint=evidence.chunk_hint,
                matched=evidence.matched,
                match_score=evidence.match_score,
                matched_chunk_ids=evidence.matched_chunk_ids,
                uttered_by_role=evidence.uttered_by_role,
                ambiguous=evidence.ambiguous,
                speaker_mismatch=evidence.speaker_mismatch,
            )
        )
    await db_session.commit()
    return extraction


def process_clinical_facts(
    facts: dict[str, Any],
    chunks: list[ClinicalExtractionChunk],
    *,
    recording_session: TranscriptionRecordingSession,
    language: str | None = None,
    grounding_stats: dict[str, Any] | None = None,
    latency_ms: int | None = None,
) -> tuple[dict[str, Any], list[ClinicalExtractionEvidenceResult], dict[str, Any]]:
    processed = deepcopy(facts)
    warnings: list[str] = []
    evidence_results: list[ClinicalExtractionEvidenceResult] = []
    stats = {
        "facts_emitted_total": 0,
        "fields_grounded": 0,
        "fields_flagged_ungrounded": 0,
        "ground_strict_forced_null": 0,
        "quotes_unmatched": 0,
        "quotes_ambiguous": 0,
        "speaker_mismatches": 0,
        "validation_warnings": 0,
        "supersessions_degraded_to_conflict": 0,
        "latency_ms": latency_ms,
    }
    if grounding_stats:
        stats.update(grounding_stats)

    seen_propositions: dict[str, str] = {}
    for fact_path, item in _iter_fact_objects(processed):
        evidence_items = item.get("evidence")
        if not isinstance(evidence_items, list):
            continue
        stats["facts_emitted_total"] += 1
        _apply_section_field_warnings(
            fact_path,
            item,
            stats=stats,
            warnings=warnings,
        )
        if apply_supports_fields_validation(
            fact_path,
            item,
            warnings,
        ):
            stats["validation_warnings"] += 1
        localized_supports: set[str] = set()
        localized_evidence_records: list[LocalizedEvidenceRecord] = []
        all_evidence_records: list[LocalizedEvidenceRecord] = []
        for evidence_index, evidence in enumerate(evidence_items):
            if not isinstance(evidence, dict):
                continue
            quote = str(evidence.get("quote") or "")
            supports_fields = [
                str(field)
                for field in evidence.get("supports_fields", [])
                if isinstance(field, str)
            ]
            chunk_hint = evidence.get("chunk_hint")
            match = _match_quote_to_chunks(
                quote,
                chunks,
                chunk_hint=str(chunk_hint) if chunk_hint else None,
            )
            speaker_mismatch = _speaker_mismatch(item, match.uttered_by_role)
            result = ClinicalExtractionEvidenceResult(
                fact_path=fact_path,
                quote=quote,
                supports_fields=supports_fields,
                chunk_hint=str(chunk_hint) if chunk_hint else None,
                matched=match.matched,
                match_score=match.match_score,
                matched_chunk_ids=match.matched_chunk_ids,
                uttered_by_role=match.uttered_by_role,
                ambiguous=match.ambiguous,
                speaker_mismatch=speaker_mismatch,
            )
            evidence_results.append(result)
            evidence_record = LocalizedEvidenceRecord(
                quote=quote,
                supports_fields=supports_fields,
                matched=result.matched,
                ambiguous=result.ambiguous,
                chunk_hint=str(chunk_hint) if chunk_hint else None,
                evidence_index=evidence_index,
            )
            all_evidence_records.append(evidence_record)
            if result.matched and not result.ambiguous:
                localized_evidence_records.append(evidence_record)
            if not result.matched:
                stats["quotes_unmatched"] += 1
                warnings.append(f"{fact_path}: quote_unmatched")
                continue
            if result.ambiguous:
                stats["quotes_ambiguous"] += 1
                warnings.append(f"{fact_path}: quote_ambiguous")
                continue
            if result.speaker_mismatch:
                stats["speaker_mismatches"] += 1
                warnings.append(f"{fact_path}: speaker_mismatch")
            localized_supports.update(supports_fields)
            _apply_ground_strict(
                item,
                evidence_quote=quote,
                supports_fields=supports_fields,
                stats=stats,
                warnings=warnings,
                fact_path=fact_path,
            )
        if apply_subject_raw_text_validation(
            fact_path,
            item,
            localized_evidence_records,
            warnings,
        ):
            stats["validation_warnings"] += 1
        if apply_collection_summary_validation(
            fact_path,
            item,
            localized_evidence_records,
            all_evidence_records,
            warnings,
        ):
            stats["validation_warnings"] += 1
        _apply_duplicate_proposition_warning(
            fact_path,
            item,
            seen_propositions=seen_propositions,
            stats=stats,
            warnings=warnings,
        )
        for field, value in item.items():
            if field == "evidence" or field in INFERRED_FIELDS or value in (None, [], {}):
                continue
            if _is_scalar(value):
                if field in localized_supports:
                    stats["fields_grounded"] += 1
                else:
                    stats["fields_flagged_ungrounded"] += 1
                    warnings.append(f"{fact_path}.{field}: field_ungrounded")

    data_quality = processed.setdefault("data_quality", {})
    if isinstance(data_quality, dict):
        existing_warnings = data_quality.get("extraction_warnings")
        if not isinstance(existing_warnings, list):
            existing_warnings = []
        data_quality["extraction_warnings"] = [*existing_warnings, *warnings]
        data_quality.setdefault("missing_critical_details", [])
    _inject_record_metadata(processed, recording_session, language=language)
    return processed, evidence_results, stats


def _build_extraction_chunks(
    transcript_json: dict[str, Any],
) -> list[ClinicalExtractionChunk]:
    chunks: list[ClinicalExtractionChunk] = []
    for section_index, chunk in enumerate(transcript_json.get("chunks", []) or []):
        if not isinstance(chunk, dict):
            continue
        base_chunk_id = str(chunk.get("chunk_id") or section_index)
        turns = chunk.get("turns")
        if not isinstance(turns, list):
            text = str(chunk.get("text") or "")
            if text:
                chunks.append(
                    ClinicalExtractionChunk(
                        chunk_id=base_chunk_id,
                        section_index=section_index,
                        speaker=_normalize_speaker(chunk.get("speaker")),
                        text=text,
                        start_time_ms=_int_or_none(chunk.get("start_ms")),
                        end_time_ms=_int_or_none(chunk.get("end_ms")),
                    )
                )
            continue
        for turn_index, turn in enumerate(turns):
            if not isinstance(turn, dict):
                continue
            text = str(turn.get("text") or "").strip()
            if not text:
                continue
            chunks.append(
                ClinicalExtractionChunk(
                    chunk_id=f"{base_chunk_id}:{turn_index}",
                    section_index=section_index,
                    speaker=_normalize_speaker(turn.get("speaker")),
                    text=text,
                    start_time_ms=_int_or_none(chunk.get("start_ms")),
                    end_time_ms=_int_or_none(chunk.get("end_ms")),
                )
            )
    return chunks


def _transcript_language(transcript_json: dict[str, Any]) -> str | None:
    value = transcript_json.get("language")
    return str(value) if value else None


def _normalize_speaker(value: object) -> str | None:
    speaker = str(value or "").strip().upper()
    return {
        "MEDICO": "clinician",
        "MÉDICO": "clinician",
        "PACIENTE": "patient",
        "ACOMPANANTE": "companion",
        "DESCONOCIDO": None,
    }.get(speaker, speaker.lower() or None)


def _int_or_none(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _iter_fact_objects(value: Any, path: str = "") -> list[tuple[str, dict[str, Any]]]:
    found: list[tuple[str, dict[str, Any]]] = []
    if isinstance(value, dict):
        if isinstance(value.get("evidence"), list):
            found.append((path or "$", value))
        for key, child in value.items():
            if key == "evidence":
                continue
            child_path = f"{path}.{key}" if path else key
            found.extend(_iter_fact_objects(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_iter_fact_objects(child, f"{path}[{index}]"))
    return found


class _QuoteMatch:
    def __init__(
        self,
        *,
        matched: bool,
        match_score: float | None = None,
        matched_chunk_ids: list[str] | None = None,
        uttered_by_role: str | None = None,
        ambiguous: bool = False,
    ) -> None:
        self.matched = matched
        self.match_score = match_score
        self.matched_chunk_ids = matched_chunk_ids or []
        self.uttered_by_role = uttered_by_role
        self.ambiguous = ambiguous


def _match_quote_to_chunks(
    quote: str,
    chunks: list[ClinicalExtractionChunk],
    *,
    chunk_hint: str | None,
) -> _QuoteMatch:
    normalized_quote = _normalize_text(quote)
    if not normalized_quote:
        return _QuoteMatch(matched=False)
    candidates = _single_turn_candidates(chunks, normalized_quote, chunk_hint)
    if not _has_viable_candidate(candidates):
        candidates = [
            *candidates,
            *_adjacent_window_candidates(chunks, normalized_quote),
        ]
    if not candidates:
        return _QuoteMatch(matched=False)
    candidates.sort(key=lambda item: item[1], reverse=True)
    best_chunks, best_score = candidates[0]
    if best_score < 82:
        return _QuoteMatch(matched=False, match_score=best_score)
    best_size = len(best_chunks)
    close_matches = [
        item
        for item in candidates
        if item[1] >= best_score - 3 and len(item[0]) == best_size
    ]
    quote_token_count = len(normalized_quote.split())
    ambiguous = quote_token_count < 3 or len(close_matches) > 1
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
    chunk_hint: str | None,
) -> list[tuple[list[ClinicalExtractionChunk], float]]:
    candidates: list[tuple[list[ClinicalExtractionChunk], float]] = []
    seen_candidate_keys: set[tuple[str, ...]] = set()
    hinted = [chunk for chunk in chunks if chunk.chunk_id == chunk_hint]
    for chunk in hinted:
        _append_match_candidate(candidates, seen_candidate_keys, [chunk], normalized_quote)
    for chunk in chunks:
        _append_match_candidate(candidates, seen_candidate_keys, [chunk], normalized_quote)
    return candidates


def _adjacent_window_candidates(
    chunks: list[ClinicalExtractionChunk],
    normalized_quote: str,
) -> list[tuple[list[ClinicalExtractionChunk], float]]:
    candidates: list[tuple[list[ClinicalExtractionChunk], float]] = []
    seen_candidate_keys: set[tuple[str, ...]] = set()
    for index in range(len(chunks) - 1):
        window = [chunks[index], chunks[index + 1]]
        _append_match_candidate(candidates, seen_candidate_keys, window, normalized_quote)
    return candidates


def _has_viable_candidate(
    candidates: list[tuple[list[ClinicalExtractionChunk], float]],
) -> bool:
    return any(score >= 82 for _chunks, score in candidates)


def _append_match_candidate(
    candidates: list[tuple[list[ClinicalExtractionChunk], float]],
    seen_candidate_keys: set[tuple[str, ...]],
    chunks: list[ClinicalExtractionChunk],
    normalized_quote: str,
) -> None:
    key = tuple(chunk.chunk_id for chunk in chunks)
    if key in seen_candidate_keys:
        return
    seen_candidate_keys.add(key)
    candidates.append(
        (
            chunks,
            _score(
                normalized_quote,
                _normalize_text(" ".join(chunk.text for chunk in chunks)),
            ),
        )
    )


def _normalize_text(value: str) -> str:
    return normalize_text(value)


def _score(quote: str, text: str) -> float:
    if not quote or not text:
        return 0.0
    if quote in text:
        return 100.0
    quote_tokens = set(quote.split())
    text_tokens = set(text.split())
    if not quote_tokens:
        return 0.0
    token_overlap = len(quote_tokens & text_tokens) / len(quote_tokens)
    sequence = SequenceMatcher(None, quote, text).ratio()
    return round(max(token_overlap, sequence) * 100, 2)


def _speaker_mismatch(item: dict[str, Any], uttered_by_role: str | None) -> bool:
    source_role = item.get("information_source_role")
    if not source_role or not uttered_by_role:
        return False
    if source_role in {"other_explicit", "prior_record"}:
        return False
    return str(source_role) != uttered_by_role


def _apply_ground_strict(
    item: dict[str, Any],
    *,
    evidence_quote: str,
    supports_fields: list[str],
    stats: dict[str, Any],
    warnings: list[str],
    fact_path: str,
) -> None:
    normalized_quote = _normalize_text(evidence_quote)
    for field in supports_fields:
        if field not in GROUND_STRICT_FIELDS:
            continue
        value = item.get(field)
        if value in (None, "", [], {}):
            continue
        if _normalize_text(str(value)) in normalized_quote:
            continue
        item[field] = None
        stats["ground_strict_forced_null"] += 1
        warnings.append(f"{fact_path}.{field}: ground_strict_forced_null")


def _apply_section_field_warnings(
    fact_path: str,
    item: dict[str, Any],
    *,
    stats: dict[str, Any],
    warnings: list[str],
) -> None:
    allowed_fields = _allowed_fields_for_path(fact_path)
    if not allowed_fields:
        return
    for field, value in list(item.items()):
        if field in allowed_fields or value in (None, [], {}):
            continue
        item[field] = None
        stats["validation_warnings"] += 1
        warnings.append(f"{fact_path}.{field}: field_not_allowed")


def _allowed_fields_for_path(fact_path: str) -> set[str] | None:
    for prefix, allowed_fields in sorted(
        PATH_ALLOWED_FIELDS.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if fact_path == prefix or fact_path.startswith(f"{prefix}["):
            return allowed_fields
    return None


def _apply_duplicate_proposition_warning(
    fact_path: str,
    item: dict[str, Any],
    *,
    seen_propositions: dict[str, str],
    stats: dict[str, Any],
    warnings: list[str],
) -> None:
    key = _proposition_key(fact_path, item)
    if not key:
        return
    previous_path = seen_propositions.get(key)
    if previous_path and _top_level_section(previous_path) != _top_level_section(fact_path):
        _nullify_duplicate_fact(item)
        stats["validation_warnings"] += 1
        warnings.append(
            f"{fact_path}: duplicate_proposition_removed:{previous_path}"
        )
        return
    seen_propositions.setdefault(key, fact_path)


def _proposition_key(fact_path: str, item: dict[str, Any]) -> str | None:
    if fact_path in {"allergy_summary", "medication_summary"}:
        return None
    concept = next(
        (
            str(item.get(field))
            for field in (
                "concept_raw_text",
                "name_raw",
                "substance_raw",
                "text_raw",
                "value_raw",
                "definition_id",
                "result_content_raw",
                "type_raw",
            )
            if item.get(field)
        ),
        "",
    )
    quote = ""
    evidence_items = item.get("evidence")
    if isinstance(evidence_items, list):
        quote = next(
            (
                str(evidence.get("quote"))
                for evidence in evidence_items
                if isinstance(evidence, dict) and evidence.get("quote")
            ),
            "",
        )
    key_parts = [_normalize_text(value) for value in (concept, quote) if value]
    return "|".join(key_parts) if key_parts else None


def _top_level_section(fact_path: str) -> str:
    return re.split(r"[.\[]", fact_path, maxsplit=1)[0]


def _is_scalar(value: Any) -> bool:
    return isinstance(value, str | int | float | bool)


def _nullify_duplicate_fact(item: dict[str, Any]) -> None:
    for field in (
        "concept_raw_text",
        "text_raw",
        "name_raw",
        "substance_raw",
        "value_raw",
        "definition_id",
        "result_content_raw",
        "type_raw",
    ):
        if field in item:
            item[field] = None


def _inject_record_metadata(
    facts: dict[str, Any],
    recording_session: TranscriptionRecordingSession,
    *,
    language: str | None = None,
) -> None:
    encounter = recording_session.encounter
    patient = getattr(encounter, "patient", None)
    facts["record_metadata"] = {
        "schema_version": SCHEMA_VERSION,
        "encounter_id": recording_session.encounter_id,
        "language": language
        or (
            facts.get("record_metadata", {}).get("language")
            if isinstance(facts.get("record_metadata"), dict)
            else None
        ),
    }
    facts["patient"] = {
        **(facts.get("patient") if isinstance(facts.get("patient"), dict) else {}),
        "id": getattr(patient, "id", None),
        "name": getattr(patient, "name", None),
    }
    facts["encounter"] = {
        "id": recording_session.encounter_id,
        "document_id": recording_session.document_id,
        "doctor_id": recording_session.doctor_id,
        "occurred_at": encounter.occurred_at.isoformat()
        if getattr(encounter, "occurred_at", None)
        else None,
    }
