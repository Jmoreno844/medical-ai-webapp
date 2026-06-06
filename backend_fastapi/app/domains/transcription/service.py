from __future__ import annotations

import difflib
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.db.models import (
    Document,
    Encounter,
    TranscriptionAudioSection,
    TranscriptionRecordingSession,
)
from app.domains.documents.content import set_document_content_fields
from app.domains.documents.sse_hub import publish_document_event
from app.domains.transcription.schemas import AudioSectionResponse
from app.domains.transcription.schemas import SectionWorkItemResponse
from app.integrations.transcription_tasks import enqueue_transcription_task

logger = logging.getLogger(__name__)

SESSION_STATUS_RECORDING = "recording"
SESSION_STATUS_FINISHING = "finishing"
SESSION_STATUS_CONSOLIDATING = "consolidating"
SESSION_STATUS_CONSOLIDATED = "consolidated"
SESSION_STATUS_NEEDS_REVIEW = "needs_review"

SECTION_STATUS_REGISTERED = "registered"
SECTION_STATUS_TRANSCRIBING = "transcribing"
SECTION_STATUS_TRANSCRIBED = "transcribed"
SECTION_STATUS_DISCARDED_NO_SPEECH = "discarded_no_speech"
SECTION_STATUS_FAILED_RETRYABLE = "failed_retryable"
SECTION_STATUS_FAILED_FINAL = "failed_final"
SECTION_COMPLETE_STATUSES = {
    SECTION_STATUS_TRANSCRIBED,
    SECTION_STATUS_DISCARDED_NO_SPEECH,
}

REMOVABLE_INLINE_TAGS = {
    "tos",
    "ruido",
    "silencio",
    "carraspeo",
    "respiracion",
    "respiración",
}


def serialize_section(section: TranscriptionAudioSection) -> AudioSectionResponse:
    return AudioSectionResponse(
        section_id=section.section_id,
        client_section_id=section.client_section_id,
        section_index=section.section_index,
        start_time_ms=section.start_time_ms,
        end_time_ms=section.end_time_ms,
        overlap_ms=section.overlap_ms,
        gcs_object_name=section.gcs_object_name,
        content_type=section.content_type,
        byte_size=section.byte_size,
        status=section.status,
        raw_transcript=section.raw_transcript,
        error_code=section.error_code,
        retry_count=section.retry_count,
        created_at=section.created_at,
        updated_at=section.updated_at,
    )


async def get_recording_session_for_doctor(
    session: AsyncSession,
    *,
    session_id: str,
    doctor_id: int,
) -> TranscriptionRecordingSession | None:
    result = await session.execute(
        select(TranscriptionRecordingSession)
        .options(selectinload(TranscriptionRecordingSession.sections))
        .where(
            TranscriptionRecordingSession.session_id == session_id,
            TranscriptionRecordingSession.doctor_id == doctor_id,
        )
    )
    return result.scalar_one_or_none()


async def get_canonical_recording_session_for_document(
    session: AsyncSession,
    *,
    document_id: int,
    doctor_id: int,
) -> TranscriptionRecordingSession | None:
    result = await session.execute(
        select(TranscriptionRecordingSession)
        .options(
            selectinload(TranscriptionRecordingSession.sections),
            selectinload(TranscriptionRecordingSession.document),
            selectinload(TranscriptionRecordingSession.encounter),
        )
        .where(
            TranscriptionRecordingSession.document_id == document_id,
            TranscriptionRecordingSession.doctor_id == doctor_id,
        )
        .order_by(TranscriptionRecordingSession.started_at.desc(), TranscriptionRecordingSession.id.desc())
    )
    return result.scalars().first()


async def create_recording_session(
    session: AsyncSession,
    *,
    encounter: Encounter,
    document: Document,
    doctor_id: int,
) -> TranscriptionRecordingSession:
    existing_session = await get_canonical_recording_session_for_document(
        session,
        document_id=document.id,
        doctor_id=doctor_id,
    )
    if existing_session:
        return existing_session

    now = datetime.now(timezone.utc)
    recording_session = TranscriptionRecordingSession(
        session_id=uuid.uuid4().hex,
        encounter_id=encounter.id,
        document_id=document.id,
        doctor_id=doctor_id,
        status=SESSION_STATUS_RECORDING,
        started_at=now,
        finished_at=None,
        finalized_at=None,
        consolidated_transcript=document.content_markdown.strip() or None,
        error_code=None,
    )
    session.add(recording_session)
    await session.flush()
    return recording_session


async def reset_recording_session(
    session: AsyncSession,
    *,
    recording_session: TranscriptionRecordingSession,
    clear_document_content: bool = False,
) -> None:
    await session.execute(
        delete(TranscriptionAudioSection).where(
            TranscriptionAudioSection.recording_session_id == recording_session.id,
        )
    )
    recording_session.status = SESSION_STATUS_RECORDING
    recording_session.started_at = datetime.now(timezone.utc)
    recording_session.finished_at = None
    recording_session.finalized_at = None
    recording_session.consolidated_transcript = None
    recording_session.error_code = None

    if recording_session.encounter:
        recording_session.encounter.has_been_transcribed = False

    if clear_document_content and recording_session.document:
        set_document_content_fields(
            recording_session.document,
            content_markdown="",
            preferred_source="markdown",
        )

    await session.flush()


async def _update_encounter_audio_duration(
    session: AsyncSession,
    *,
    encounter_id: int,
    end_time_ms: int,
) -> None:
    duration_seconds = int((end_time_ms + 999) // 1000)
    result = await session.execute(
        select(Encounter).where(Encounter.id == encounter_id)
    )
    encounter = result.scalar_one_or_none()
    if encounter:
        encounter.audio_duration_seconds = max(
            encounter.audio_duration_seconds or 0,
            duration_seconds,
        )


def build_section_object_name(
    *,
    encounter_id: int,
    session_id: str,
    client_section_id: str,
    section_index: int,
) -> str:
    safe_client_id = "".join(
        char for char in client_section_id if char.isalnum() or char in {"-", "_"}
    )[:64]
    return (
        f"encounter_audio/{encounter_id}/sessions/{session_id}/sections/"
        f"{section_index:06d}-{safe_client_id or uuid.uuid4().hex}.webm"
    )


def generate_section_upload_url(
    *,
    settings: Settings,
    gcs_object_name: str,
    content_type: str,
) -> str:
    from app.integrations.storage import generate_v4_upload_signed_url

    return generate_v4_upload_signed_url(
        settings=settings,
        gcs_object_name=gcs_object_name,
        content_type=content_type,
    )


async def register_audio_section(
    session: AsyncSession,
    *,
    recording_session: TranscriptionRecordingSession,
    client_section_id: str,
    section_index: int,
    start_time_ms: int,
    end_time_ms: int,
    overlap_ms: int,
    gcs_object_name: str,
    content_type: str,
    byte_size: int | None,
) -> TranscriptionAudioSection:
    now = datetime.now(timezone.utc)
    encounter_id = recording_session.encounter_id
    existing = await session.execute(
        select(TranscriptionAudioSection).where(
            TranscriptionAudioSection.recording_session_id == recording_session.id,
            TranscriptionAudioSection.client_section_id == client_section_id,
        )
    )
    section = existing.scalar_one_or_none()
    if section:
        await _update_encounter_audio_duration(
            session,
            encounter_id=encounter_id,
            end_time_ms=section.end_time_ms,
        )
        return section

    section = TranscriptionAudioSection(
        section_id=uuid.uuid4().hex,
        recording_session_id=recording_session.id,
        client_section_id=client_section_id,
        section_index=section_index,
        start_time_ms=start_time_ms,
        end_time_ms=end_time_ms,
        overlap_ms=overlap_ms,
        gcs_object_name=gcs_object_name,
        content_type=content_type,
        byte_size=byte_size,
        status=SECTION_STATUS_REGISTERED,
        raw_transcript=None,
        error_code=None,
        retry_count=0,
        created_at=now,
        updated_at=now,
    )
    session.add(section)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        result = await session.execute(
            select(TranscriptionAudioSection).where(
                TranscriptionAudioSection.recording_session_id == recording_session.id,
                (
                    TranscriptionAudioSection.client_section_id == client_section_id
                )
                | (TranscriptionAudioSection.section_index == section_index),
            )
        )
        existing_after_race = result.scalar_one_or_none()
        if existing_after_race:
            await _update_encounter_audio_duration(
                session,
                encounter_id=encounter_id,
                end_time_ms=existing_after_race.end_time_ms,
            )
            return existing_after_race
        raise
    await _update_encounter_audio_duration(
        session,
        encounter_id=encounter_id,
        end_time_ms=end_time_ms,
    )
    return section


def _task_base_url(settings: Settings) -> str:
    if not settings.transcription_task_target_url:
        raise ValueError("TRANSCRIPTION_TASK_TARGET_URL is not configured")
    return settings.transcription_task_target_url.rstrip("/")


def enqueue_section_task(section: TranscriptionAudioSection, settings: Settings) -> str:
    target_url = f"{_task_base_url(settings)}/sections/{section.section_id}"
    return enqueue_transcription_task(
        {"section_id": section.section_id},
        settings=settings,
        target_url=target_url,
    )


def _merge_with_light_dedup(previous: str, next_text: str) -> str:
    previous = previous.rstrip()
    next_text = next_text.strip()
    if not previous:
        return next_text
    if not next_text:
        return previous

    max_overlap = min(len(previous), len(next_text), 240)
    for size in range(max_overlap, 5, -1):
        if previous[-size:].lower() == next_text[:size].lower():
            return f"{previous}{next_text[size:]}"

    tail_words = previous.split()[-16:]
    head_words = next_text.split()[:16]
    matcher = difflib.SequenceMatcher(None, tail_words, head_words, autojunk=False)
    match = matcher.find_longest_match(0, len(tail_words), 0, len(head_words))
    if match.size >= 4 and match.b == 0 and match.a + match.size == len(tail_words):
        return f"{' '.join(previous.split()[:-match.size])} {next_text}".strip()

    return f"{previous}\n\n{next_text}"


def _normalize_transcript_for_document(transcript: str | None) -> str:
    if not transcript:
        return ""

    def replace_tag(match: re.Match[str]) -> str:
        tag = match.group(1).strip().lower()
        if tag in REMOVABLE_INLINE_TAGS:
            return " "
        return match.group(0)

    normalized = re.sub(r"\[\s*([^\[\]]+?)\s*\]", replace_tag, transcript)
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"\s+([,.;:!?])", r"\1", normalized)
    normalized = normalized.strip()

    if re.fullmatch(r"(?:\[[^\[\]]+\]\s*)+", normalized):
        return ""

    return normalized


def _merge_session_with_existing_document(
    recording_session: TranscriptionRecordingSession,
    session_transcript: str,
) -> str:
    base_transcript = _normalize_transcript_for_document(
        recording_session.consolidated_transcript
    )
    if not base_transcript:
        return session_transcript
    if not session_transcript:
        return base_transcript
    return _merge_with_light_dedup(base_transcript, session_transcript)


def is_recording_session_ready_for_consolidation(
    recording_session: TranscriptionRecordingSession,
) -> bool:
    return (
        bool(recording_session.finished_at)
        and bool(recording_session.sections)
        and all(
            item.status in SECTION_COMPLETE_STATUSES
            for item in recording_session.sections
        )
    )


async def get_section_work_item(
    db_session: AsyncSession,
    *,
    section_id: str,
    settings: Settings,
) -> SectionWorkItemResponse | None:
    result = await db_session.execute(
        select(TranscriptionAudioSection)
        .options(selectinload(TranscriptionAudioSection.recording_session))
        .where(TranscriptionAudioSection.section_id == section_id)
    )
    section = result.scalar_one_or_none()
    if not section:
        return None
    if not settings.gcs_bucket_name:
        raise ValueError("GCS_BUCKET_NAME is required for transcription worker")
    recording_session = section.recording_session
    return SectionWorkItemResponse(
        section_id=section.section_id,
        session_id=recording_session.session_id,
        encounter_id=recording_session.encounter_id,
        document_id=recording_session.document_id,
        section_index=section.section_index,
        gcs_object_name=section.gcs_object_name,
        gcs_uri=f"gs://{settings.gcs_bucket_name}/{section.gcs_object_name}",
        content_type=section.content_type,
    )


async def apply_section_worker_result(
    db_session: AsyncSession,
    *,
    section_id: str,
    status: str,
    transcript: str | None,
    error_code: str | None,
    settings: Settings,
) -> TranscriptionAudioSection | None:
    result = await db_session.execute(
        select(TranscriptionAudioSection)
        .options(
            selectinload(TranscriptionAudioSection.recording_session).selectinload(
                TranscriptionRecordingSession.sections
            ),
            selectinload(TranscriptionAudioSection.recording_session).selectinload(
                TranscriptionRecordingSession.document
            ),
        )
        .where(TranscriptionAudioSection.section_id == section_id)
    )
    section = result.scalar_one_or_none()
    if not section:
        return None
    if section.status in SECTION_COMPLETE_STATUSES:
        return section

    section.updated_at = datetime.now(timezone.utc)
    if status == SECTION_STATUS_DISCARDED_NO_SPEECH:
        section.raw_transcript = ""
        section.status = SECTION_STATUS_DISCARDED_NO_SPEECH
        section.error_code = error_code or "no_speech_detected"
    elif status == SECTION_STATUS_TRANSCRIBED:
        section.raw_transcript = _normalize_transcript_for_document(transcript)
        section.status = SECTION_STATUS_TRANSCRIBED
        section.error_code = error_code
    elif status == SECTION_STATUS_FAILED_FINAL:
        section.status = SECTION_STATUS_FAILED_FINAL
        section.error_code = error_code or "worker_failed_final"
        await db_session.commit()
        return section
    else:
        section.status = SECTION_STATUS_FAILED_RETRYABLE
        section.error_code = error_code or "worker_failed_retryable"
        await db_session.commit()
        return section

    recording_session = section.recording_session
    await db_session.commit()

    ordered_transcripts = [
        _normalize_transcript_for_document(item.raw_transcript)
        for item in sorted(recording_session.sections, key=lambda item: item.section_index)
    ]
    session_streaming_content = ""
    for item in ordered_transcripts:
        if not item:
            continue
        session_streaming_content = _merge_with_light_dedup(
            session_streaming_content,
            item,
        )
    streaming_content = _merge_session_with_existing_document(
        recording_session,
        session_streaming_content,
    )

    # Persist the merged partial transcript so refresh/HMR can recover the last
    # realtime text even before the final consolidation finishes.
    set_document_content_fields(
        recording_session.document,
        content_markdown=streaming_content,
        preferred_source="markdown",
    )
    await db_session.commit()

    await publish_document_event(
        recording_session.document_id,
        "transcription_update",
        {"content": streaming_content},
    )
    if is_recording_session_ready_for_consolidation(recording_session):
        try:
            await consolidate_recording_session(
                db_session,
                session_id=recording_session.session_id,
            )
        except Exception:
            logger.exception(
                "Failed to finalize recording session after section %s",
                section.section_id,
            )
    return section


async def consolidate_recording_session(
    db_session: AsyncSession,
    *,
    session_id: str,
) -> TranscriptionRecordingSession | None:
    result = await db_session.execute(
        select(TranscriptionRecordingSession)
        .options(
            selectinload(TranscriptionRecordingSession.sections),
            selectinload(TranscriptionRecordingSession.document),
            selectinload(TranscriptionRecordingSession.encounter),
        )
        .where(TranscriptionRecordingSession.session_id == session_id)
    )
    recording_session = result.scalar_one_or_none()
    if not recording_session:
        return None
    if recording_session.status == SESSION_STATUS_CONSOLIDATED:
        return recording_session

    sections = sorted(recording_session.sections, key=lambda item: item.section_index)
    if any(section.status == SECTION_STATUS_FAILED_FINAL for section in sections):
        recording_session.status = SESSION_STATUS_NEEDS_REVIEW
        recording_session.error_code = "section_failed_final"
        await db_session.commit()
        return recording_session

    if any(section.status not in SECTION_COMPLETE_STATUSES for section in sections):
        recording_session.status = SESSION_STATUS_FINISHING
        recording_session.error_code = "sections_pending"
        await db_session.commit()
        raise RuntimeError("sections_pending")

    recording_session.status = SESSION_STATUS_CONSOLIDATING
    await db_session.commit()

    session_transcript = ""
    for section in sections:
        if section.status != SECTION_STATUS_TRANSCRIBED:
            continue
        normalized = _normalize_transcript_for_document(section.raw_transcript)
        if not normalized:
            continue
        session_transcript = _merge_with_light_dedup(
            session_transcript,
            normalized,
        )

    consolidated = _merge_session_with_existing_document(
        recording_session,
        session_transcript,
    )
    if consolidated.strip():
        set_document_content_fields(
            recording_session.document,
            content_markdown=consolidated,
            preferred_source="markdown",
        )
    recording_session.consolidated_transcript = consolidated
    recording_session.status = SESSION_STATUS_CONSOLIDATED
    recording_session.finalized_at = datetime.now(timezone.utc)
    recording_session.error_code = None
    recording_session.encounter.has_been_transcribed = True
    await db_session.commit()
    await publish_document_event(recording_session.document_id, "transcription_complete")
    return recording_session
