from __future__ import annotations

import difflib
import json
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
from app.domains.transcription.schemas import (
    AudioSectionResponse,
    ChunkTranscriptResponse,
    SectionWorkItemResponse,
    TranscriptionTurnResponse,
)
from transcription_contract.consolidate import (
    SectionTurnsData,
    build_chunks_from_sections,
    dedupe_adjacent_chunks,
)
from transcription_contract.models import ChunkTranscript, ConsultationTranscript, TranscriptionTurn
from transcription_contract.render import render_turns_to_clinical_text
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
SECTION_STATUS_DISCARDED_NO_SPEECH = "discarded_no_speech"
SECTION_STATUS_FAILED_RETRYABLE = "failed_retryable"
SECTION_STATUS_FAILED_FINAL = "failed_final"
SECTION_COMPLETE_STATUSES = {
    SECTION_STATUS_TRANSCRIBED,
    SECTION_STATUS_DISCARDED_NO_SPEECH,
}
WORKER_SUCCESS_STATUSES = {
    SECTION_STATUS_TRANSCRIBED,
    SECTION_STATUS_DISCARDED_NO_SPEECH,
}
SECTION_STUCK_STATUSES = {
    SECTION_STATUS_REGISTERED,
    SECTION_STATUS_TRANSCRIBING,
}
SECTION_RETRYABLE_STATUSES = {
    SECTION_STATUS_REGISTERED,
    SECTION_STATUS_TRANSCRIBING,
    SECTION_STATUS_FAILED_RETRYABLE,
    SECTION_STATUS_FAILED_FINAL,
}

STUCK_SECTION_THRESHOLD_SECONDS = 120
STUCK_SECTION_MANUAL_RETRY_THRESHOLD_SECONDS = 90
MAX_MANUAL_SECTION_RETRIES = 3

TRANSCRIPTION_ERROR_MESSAGES: dict[str, str] = {
    "section_dispatch_failed": (
        "No se pudo iniciar la transcripción del audio. "
        "El audio de la consulta se conservó."
    ),
    "section_failed_final": (
        "No se pudo completar la transcripción. "
        "El audio de la consulta se conservó."
    ),
    "task_dispatch_exhausted": (
        "No se pudo completar la transcripción tras varios intentos automáticos. "
        "El audio de la consulta se conservó."
    ),
    "worker_failed_final": (
        "No se pudo procesar una sección de audio. "
        "El audio de la consulta se conservó."
    ),
    "manual_retry_exhausted": (
        "No se pudo transcribir tras varios intentos. "
        "Grabe la consulta nuevamente o contacte soporte."
    ),
    "audio_expired": "El audio expiró. Grabe la consulta nuevamente.",
    "session_not_retryable": "Esta sesión de transcripción no admite reintento.",
    "no_retryable_sections": "No hay secciones de audio disponibles para reintentar.",
}


def transcription_user_message(error_code: str | None) -> str:
    if not error_code:
        return TRANSCRIPTION_ERROR_MESSAGES["section_failed_final"]
    return TRANSCRIPTION_ERROR_MESSAGES.get(
        error_code,
        "No se pudo completar la transcripción. El audio de la consulta se conservó.",
    )


async def publish_transcription_error(
    document_id: int,
    error_code: str,
    *,
    error: str | None = None,
) -> None:
    await publish_document_event(
        document_id,
        "transcription_error",
        {
            "error": error or transcription_user_message(error_code),
            "error_code": error_code,
        },
    )

REMOVABLE_INLINE_TAGS = {
    "tos",
    "ruido",
    "silencio",
    "carraspeo",
    "respiracion",
    "respiración",
}


def _deserialize_turns(
    turns_json: list[dict[str, object]] | None,
) -> list[TranscriptionTurn] | None:
    if turns_json is None:
        return None
    return [TranscriptionTurn.model_validate(item) for item in turns_json]


def _section_turns(section: TranscriptionAudioSection) -> list[TranscriptionTurn]:
    if section.turns_json is not None:
        return _deserialize_turns(section.turns_json) or []
    if section.raw_transcript:
        text = section.raw_transcript.strip()
        if text:
            return [TranscriptionTurn(speaker="DESCONOCIDO", text=text)]
    return []


def _serialize_turns(
    turns: list[TranscriptionTurn] | None,
) -> list[TranscriptionTurnResponse] | None:
    if turns is None:
        return None
    return [
        TranscriptionTurnResponse(
            speaker=turn.speaker,
            text=turn.text,
            overlaps_previous=turn.overlaps_previous,
            overlaps_next=turn.overlaps_next,
        )
        for turn in turns
    ]


def _chunk_to_response(chunk: ChunkTranscript) -> ChunkTranscriptResponse:
    return ChunkTranscriptResponse(
        chunk_id=chunk.chunk_id,
        start_ms=chunk.start_ms,
        end_ms=chunk.end_ms,
        turns=_serialize_turns(chunk.turns) or [],
    )


def _chunks_to_dict(chunks: list[ChunkTranscript]) -> list[dict[str, object]]:
    return [chunk.model_dump() for chunk in chunks]


def _build_session_chunks(
    recording_session: TranscriptionRecordingSession,
) -> list[ChunkTranscript]:
    sections_data = [
        SectionTurnsData(
            section_id=section.section_id,
            section_index=section.section_index,
            start_ms=section.start_time_ms,
            end_ms=section.end_time_ms,
            turns=_section_turns(section),
            status=section.status,
        )
        for section in sorted(
            recording_session.sections,
            key=lambda item: item.section_index,
        )
    ]
    return dedupe_adjacent_chunks(build_chunks_from_sections(sections_data))


def _persist_session_transcript_json(
    recording_session: TranscriptionRecordingSession,
    chunks: list[ChunkTranscript],
) -> None:
    consultation = ConsultationTranscript(
        session_id=recording_session.session_id,
        chunks=chunks,
    )
    recording_session.transcript_json = consultation.model_dump()


async def resolve_transcription_content_for_generation(
    session: AsyncSession,
    *,
    document_id: int,
    doctor_id: int,
    fallback_markdown: str | None,
) -> str:
    recording_session = await get_canonical_recording_session_for_document(
        session,
        document_id=document_id,
        doctor_id=doctor_id,
    )
    if recording_session and recording_session.transcript_json:
        consultation = ConsultationTranscript.model_validate(
            recording_session.transcript_json
        )
        rendered = render_turns_to_clinical_text(consultation.chunks)
        if rendered.strip():
            return rendered

    if fallback_markdown and fallback_markdown.strip():
        return fallback_markdown.strip()

    return ""


def serialize_session_chunks(
    recording_session: TranscriptionRecordingSession,
) -> list[ChunkTranscriptResponse]:
    if recording_session.transcript_json:
        consultation = ConsultationTranscript.model_validate(
            recording_session.transcript_json
        )
        return [_chunk_to_response(chunk) for chunk in consultation.chunks]
    return [_chunk_to_response(chunk) for chunk in _build_session_chunks(recording_session)]


def serialize_section(section: TranscriptionAudioSection) -> AudioSectionResponse:
    turns = (
        _deserialize_turns(section.turns_json)
        if section.turns_json is not None
        else None
    )
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
        original_gcs_object_name=section.original_gcs_object_name,
        original_content_type=section.original_content_type,
        original_byte_size=section.original_byte_size,
        clipped_gcs_object_name=section.clipped_gcs_object_name,
        clipped_content_type=section.clipped_content_type,
        clipped_byte_size=section.clipped_byte_size,
        transcription_source_gcs_object_name=section.transcription_source_gcs_object_name,
        frontend_vad_metadata=(
            json.loads(section.frontend_vad_metadata_json)
            if section.frontend_vad_metadata_json
            else None
        ),
        transcription_source=section.transcription_source,
        status=section.status,
        turns=_serialize_turns(turns),
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
    recording_session.transcript_json = None
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


def build_section_object_names(
    *,
    encounter_id: int,
    session_id: str,
    client_section_id: str,
    section_index: int,
    original_content_type: str,
    clipped_content_type: str,
) -> tuple[str, str]:
    safe_client_id = "".join(
        char for char in client_section_id if char.isalnum() or char in {"-", "_"}
    )[:64]
    base = (
        f"encounters/{encounter_id}/sessions/{session_id}/sections/"
        f"{section_index:06d}_{safe_client_id or uuid.uuid4().hex}"
    )
    return (
        f"{base}/original{_extension_for_content_type(original_content_type)}",
        f"{base}/clipped{_extension_for_content_type(clipped_content_type)}",
    )


def _extension_for_content_type(content_type: str) -> str:
    normalized = content_type.split(";", 1)[0].strip().lower()
    if normalized == "audio/webm":
        return ".webm"
    if normalized in {"audio/ogg", "audio/opus"}:
        return ".ogg"
    if normalized in {"audio/mp4", "audio/aac", "audio/x-m4a", "audio/m4a"}:
        return ".m4a"
    if normalized == "audio/wav":
        return ".wav"
    return ".audio"


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
    original_gcs_object_name: str,
    original_content_type: str,
    original_byte_size: int | None,
    clipped_gcs_object_name: str,
    clipped_content_type: str,
    clipped_byte_size: int | None,
    transcription_source_gcs_object_name: str,
    frontend_vad_metadata: dict | None,
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
        gcs_object_name=transcription_source_gcs_object_name,
        content_type=clipped_content_type,
        byte_size=clipped_byte_size,
        original_gcs_object_name=original_gcs_object_name,
        original_content_type=original_content_type,
        original_byte_size=original_byte_size,
        clipped_gcs_object_name=clipped_gcs_object_name,
        clipped_content_type=clipped_content_type,
        clipped_byte_size=clipped_byte_size,
        transcription_source_gcs_object_name=transcription_source_gcs_object_name,
        frontend_vad_metadata_json=(
            json.dumps(frontend_vad_metadata, ensure_ascii=True)
            if frontend_vad_metadata is not None
            else None
        ),
        transcription_source="clipped_frontend",
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
        original_gcs_object_name=section.original_gcs_object_name,
        original_gcs_uri=(
            f"gs://{settings.gcs_bucket_name}/{section.original_gcs_object_name}"
            if section.original_gcs_object_name
            else None
        ),
        original_content_type=section.original_content_type,
        clipped_gcs_object_name=section.clipped_gcs_object_name,
        clipped_gcs_uri=(
            f"gs://{settings.gcs_bucket_name}/{section.clipped_gcs_object_name}"
            if section.clipped_gcs_object_name
            else None
        ),
        clipped_content_type=section.clipped_content_type,
        transcription_source_gcs_object_name=(
            section.transcription_source_gcs_object_name or section.gcs_object_name
        ),
        transcription_source_gcs_uri=(
            f"gs://{settings.gcs_bucket_name}/"
            f"{section.transcription_source_gcs_object_name or section.gcs_object_name}"
        ),
        transcription_source_content_type=section.content_type,
    )


async def apply_section_worker_result(
    db_session: AsyncSession,
    *,
    section_id: str,
    status: str,
    turns: list[TranscriptionTurnResponse] | None,
    error_code: str | None,
    transcription_source: str | None,
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
    if transcription_source:
        section.transcription_source = transcription_source
    if status == SECTION_STATUS_DISCARDED_NO_SPEECH:
        section.turns_json = []
        section.raw_transcript = None
        section.status = SECTION_STATUS_DISCARDED_NO_SPEECH
        section.error_code = error_code or "no_speech_detected"
    elif status == SECTION_STATUS_TRANSCRIBED:
        parsed_turns = [
            TranscriptionTurn.model_validate(turn.model_dump()) for turn in (turns or [])
        ]
        section.turns_json = [turn.model_dump() for turn in parsed_turns]
        section.raw_transcript = None
        section.status = SECTION_STATUS_TRANSCRIBED
        section.error_code = error_code
    elif status == SECTION_STATUS_FAILED_FINAL:
        section.status = SECTION_STATUS_FAILED_FINAL
        section.error_code = error_code or "worker_failed_final"
        recording_session = section.recording_session
        recording_session.status = SESSION_STATUS_NEEDS_REVIEW
        recording_session.error_code = "section_failed_final"
        await db_session.commit()
        await publish_transcription_error(
            recording_session.document_id,
            section.error_code,
        )
        return section
    else:
        section.status = SECTION_STATUS_FAILED_RETRYABLE
        section.error_code = error_code or "worker_failed_retryable"
        await db_session.commit()
        return section

    recording_session = section.recording_session
    await db_session.commit()

    streaming_chunks = _build_session_chunks(recording_session)
    _persist_session_transcript_json(recording_session, streaming_chunks)
    streaming_content = render_turns_to_clinical_text(streaming_chunks)
    if recording_session.consolidated_transcript:
        streaming_content = _merge_session_with_existing_document(
            recording_session,
            streaming_content,
        )

    set_document_content_fields(
        recording_session.document,
        content_markdown=streaming_content,
        preferred_source="markdown",
    )
    recording_session.consolidated_transcript = streaming_content or None
    await db_session.commit()

    latest_chunk = streaming_chunks[-1] if streaming_chunks else None
    await publish_document_event(
        recording_session.document_id,
        "transcription_update",
        {
            "chunks": _chunks_to_dict(streaming_chunks),
            "latest_chunk": latest_chunk.model_dump() if latest_chunk else None,
            "rendered_text": streaming_content,
            "content": streaming_content,
        },
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
        await publish_transcription_error(
            recording_session.document_id,
            recording_session.error_code,
        )
        return recording_session

    if any(section.status not in SECTION_COMPLETE_STATUSES for section in sections):
        recording_session.status = SESSION_STATUS_FINISHING
        recording_session.error_code = "sections_pending"
        await db_session.commit()
        raise RuntimeError("sections_pending")

    recording_session.status = SESSION_STATUS_CONSOLIDATING
    await db_session.commit()

    consolidated_chunks = _build_session_chunks(recording_session)
    _persist_session_transcript_json(recording_session, consolidated_chunks)
    consolidated = render_turns_to_clinical_text(consolidated_chunks)
    if recording_session.consolidated_transcript and not consolidated_chunks:
        consolidated = _merge_session_with_existing_document(recording_session, "")
    elif recording_session.consolidated_transcript:
        consolidated = _merge_session_with_existing_document(
            recording_session,
            consolidated,
        )
    if consolidated.strip():
        set_document_content_fields(
            recording_session.document,
            content_markdown=consolidated,
            preferred_source="markdown",
        )
    recording_session.consolidated_transcript = consolidated or None
    recording_session.status = SESSION_STATUS_CONSOLIDATED
    recording_session.finalized_at = datetime.now(timezone.utc)
    recording_session.error_code = None
    recording_session.encounter.has_been_transcribed = True
    await db_session.commit()
    await publish_document_event(
        recording_session.document_id,
        "transcription_complete",
        {
            "chunks": _chunks_to_dict(consolidated_chunks),
            "rendered_text": consolidated,
        },
    )
    return recording_session


async def reconcile_stuck_transcription_sections(
    db_session: AsyncSession,
    recording_session: TranscriptionRecordingSession,
    *,
    now: datetime | None = None,
) -> bool:
    if recording_session.status in {
        SESSION_STATUS_CONSOLIDATED,
        SESSION_STATUS_NEEDS_REVIEW,
    }:
        return False
    if recording_session.status != SESSION_STATUS_FINISHING:
        return False
    if not recording_session.finished_at:
        return False

    current_time = now or datetime.now(timezone.utc)
    reference_time = recording_session.finished_at
    changed = False

    for section in recording_session.sections:
        if section.status not in SECTION_STUCK_STATUSES:
            continue
        retry_count = getattr(section, "retry_count", 0) or 0
        threshold_seconds = (
            STUCK_SECTION_MANUAL_RETRY_THRESHOLD_SECONDS
            if retry_count > 0
            else STUCK_SECTION_THRESHOLD_SECONDS
        )
        age_base = max(section.updated_at, reference_time)
        if current_time - age_base < timedelta(seconds=threshold_seconds):
            continue
        section.status = SECTION_STATUS_FAILED_FINAL
        section.error_code = "task_dispatch_exhausted"
        section.updated_at = current_time
        changed = True

    if not changed:
        return False

    recording_session.status = SESSION_STATUS_NEEDS_REVIEW
    recording_session.error_code = "section_failed_final"
    await db_session.commit()
    await publish_transcription_error(
        recording_session.document_id,
        "task_dispatch_exhausted",
    )
    return True


def _is_encounter_audio_expired(encounter: Encounter, *, now: datetime | None = None) -> bool:
    if not encounter.audio_expires_at:
        return False
    current_time = now or datetime.now(timezone.utc)
    return encounter.audio_expires_at <= current_time


async def retry_failed_transcription_session(
    db_session: AsyncSession,
    recording_session: TranscriptionRecordingSession,
    *,
    settings: Settings,
) -> tuple[bool, str | None, list[TranscriptionAudioSection]]:
    if recording_session.status not in {
        SESSION_STATUS_NEEDS_REVIEW,
        SESSION_STATUS_FINISHING,
    }:
        return False, "session_not_retryable", []

    encounter_result = await db_session.execute(
        select(Encounter).where(Encounter.id == recording_session.encounter_id)
    )
    encounter = encounter_result.scalar_one_or_none()
    if encounter and _is_encounter_audio_expired(encounter):
        return False, "audio_expired", []

    eligible_sections = [
        section
        for section in recording_session.sections
        if section.status in SECTION_RETRYABLE_STATUSES and section.gcs_object_name
    ]
    if not eligible_sections:
        return False, "no_retryable_sections", []

    if any(
        section.retry_count >= MAX_MANUAL_SECTION_RETRIES
        for section in eligible_sections
    ):
        return False, "manual_retry_exhausted", []

    if not should_use_cloud_tasks(settings) and not settings.transcription_worker_base_url:
        return False, "section_dispatch_failed", []

    now = datetime.now(timezone.utc)
    local_sections: list[TranscriptionAudioSection] = []
    for section in eligible_sections:
        section.status = SECTION_STATUS_REGISTERED
        section.error_code = None
        section.retry_count += 1
        section.updated_at = now
        if should_use_cloud_tasks(settings):
            try:
                enqueue_section_task(section, settings)
            except Exception:
                logger.exception(
                    "Failed to enqueue retried section transcription: %s",
                    section.section_id,
                )
                return False, "section_dispatch_failed", []
        else:
            local_sections.append(section)

    recording_session.status = SESSION_STATUS_FINISHING
    recording_session.error_code = None
    await db_session.commit()
    return True, None, local_sections
