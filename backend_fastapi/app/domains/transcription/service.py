from __future__ import annotations

import difflib
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
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
from app.domains.transcription.gemini_async import (
    consolidate_transcripts,
    transcribe_gcs_audio,
)
from app.domains.transcription.schemas import AudioSectionResponse
from app.integrations.transcription_tasks import (
    enqueue_transcription_task,
    should_use_cloud_tasks,
)

logger = logging.getLogger(__name__)

SESSION_STATUS_RECORDING = "recording"
SESSION_STATUS_FINISHING = "finishing"
SESSION_STATUS_CONSOLIDATING = "consolidating"
SESSION_STATUS_CONSOLIDATED = "consolidated"
SESSION_STATUS_NEEDS_REVIEW = "needs_review"

SECTION_STATUS_REGISTERED = "registered"
SECTION_STATUS_TRANSCRIBING = "transcribing"
SECTION_STATUS_TRANSCRIBED = "transcribed"
SECTION_STATUS_FAILED_RETRYABLE = "failed_retryable"
SECTION_STATUS_FAILED_FINAL = "failed_final"

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


async def create_recording_session(
    session: AsyncSession,
    *,
    encounter: Encounter,
    document: Document,
    doctor_id: int,
) -> TranscriptionRecordingSession:
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
    from app.integrations.storage import get_storage_client

    storage_client = get_storage_client(settings)
    bucket = storage_client.bucket(settings.gcs_bucket_name)
    blob = bucket.blob(gcs_object_name)
    return blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=10),
        method="PUT",
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
                TranscriptionAudioSection.recording_session_id
                == recording_session.id,
                TranscriptionAudioSection.client_section_id == client_section_id,
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


def enqueue_session_consolidation_task(
    recording_session: TranscriptionRecordingSession,
    settings: Settings,
) -> str:
    target_url = (
        f"{_task_base_url(settings)}/sessions/"
        f"{recording_session.session_id}/consolidate"
    )
    return enqueue_transcription_task(
        {"session_id": recording_session.session_id},
        settings=settings,
        target_url=target_url,
    )


def enqueue_legacy_audio_task(
    *,
    document_id: int,
    encounter_id: int,
    doctor_id: int,
    settings: Settings,
) -> str:
    target_url = f"{_task_base_url(settings)}/legacy-audio"
    return enqueue_transcription_task(
        {
            "document_id": document_id,
            "encounter_id": encounter_id,
            "doctor_id": doctor_id,
        },
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
    return bool(recording_session.finished_at) and all(
        item.status == SECTION_STATUS_TRANSCRIBED for item in recording_session.sections
    )


async def process_section_transcription(
    db_session: AsyncSession,
    *,
    section_id: str,
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
    if section.status == SECTION_STATUS_TRANSCRIBED:
        return section

    section.status = SECTION_STATUS_TRANSCRIBING
    section.retry_count += 1
    section.updated_at = datetime.now(timezone.utc)
    await db_session.commit()

    try:
        transcript = await transcribe_gcs_audio(
            gcs_uri=f"gs://{settings.gcs_bucket_name}/{section.gcs_object_name}",
            content_type=section.content_type,
            settings=settings,
        )
    except ValueError as exc:
        section.status = SECTION_STATUS_FAILED_FINAL
        section.error_code = str(exc)
        section.updated_at = datetime.now(timezone.utc)
        await db_session.commit()
        return section
    except Exception:
        logger.exception("Retryable transcription error for section %s", section_id)
        section.status = SECTION_STATUS_FAILED_RETRYABLE
        section.error_code = "transcription_error"
        section.updated_at = datetime.now(timezone.utc)
        await db_session.commit()
        raise

    section.raw_transcript = transcript
    section.status = SECTION_STATUS_TRANSCRIBED
    section.error_code = None
    section.updated_at = datetime.now(timezone.utc)
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
            if should_use_cloud_tasks(settings):
                enqueue_session_consolidation_task(recording_session, settings)
            else:
                await consolidate_recording_session(
                    db_session,
                    session_id=recording_session.session_id,
                    settings=settings,
                )
        except Exception:
            logger.exception(
                "Failed to enqueue consolidation after section %s",
                section.section_id,
            )
    return section


async def consolidate_recording_session(
    db_session: AsyncSession,
    *,
    session_id: str,
    settings: Settings,
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

    if any(section.status != SECTION_STATUS_TRANSCRIBED for section in sections):
        recording_session.status = SESSION_STATUS_FINISHING
        recording_session.error_code = "sections_pending"
        await db_session.commit()
        raise RuntimeError("sections_pending")

    recording_session.status = SESSION_STATUS_CONSOLIDATING
    await db_session.commit()

    ordered_transcripts = [
        _normalize_transcript_for_document(section.raw_transcript) for section in sections
    ]
    try:
        consolidated = await consolidate_transcripts(
            ordered_transcripts=ordered_transcripts,
            settings=settings,
        )
    except Exception:
        logger.exception("Consolidation failed for session %s", session_id)
        recording_session.status = SESSION_STATUS_NEEDS_REVIEW
        recording_session.error_code = "consolidation_error"
        await db_session.commit()
        raise

    consolidated = _merge_session_with_existing_document(recording_session, consolidated)
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


async def process_legacy_audio_transcription(
    db_session: AsyncSession,
    *,
    document_id: int,
    encounter_id: int,
    doctor_id: int,
    settings: Settings,
) -> bool:
    result = await db_session.execute(
        select(Document)
        .options(selectinload(Document.encounter))
        .where(
            Document.id == document_id,
            Document.doctor_id == doctor_id,
            Document.encounter_id == encounter_id,
        )
    )
    document = result.scalar_one_or_none()
    if not document or not document.encounter.audio_file_name:
        return False
    if document.encounter.has_been_transcribed and document.content_markdown.strip():
        return True

    transcript = await transcribe_gcs_audio(
        gcs_uri=f"gs://{settings.gcs_bucket_name}/{document.encounter.audio_file_name}",
        content_type="audio/webm",
        settings=settings,
    )
    set_document_content_fields(
        document,
        content_markdown=transcript,
        preferred_source="markdown",
    )
    document.encounter.has_been_transcribed = True
    await db_session.commit()
    await publish_document_event(document.id, "transcription_complete")
    return True
