from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.domains.transcription import service as transcription_service
from app.domains.transcription.service import (
    SECTION_STATUS_FAILED_FINAL,
    SECTION_STATUS_REGISTERED,
    SECTION_STATUS_TRANSCRIBING,
    SESSION_STATUS_FINISHING,
    SESSION_STATUS_NEEDS_REVIEW,
    STUCK_SECTION_MANUAL_RETRY_THRESHOLD_SECONDS,
    STUCK_SECTION_THRESHOLD_SECONDS,
    _merge_session_with_existing_document,
    _merge_with_light_dedup,
    _normalize_transcript_for_document,
    create_recording_session,
    is_recording_session_ready_for_consolidation,
    reconcile_stuck_transcription_sections,
    register_audio_section,
    reset_recording_session,
    retry_failed_transcription_session,
    transcription_user_message,
)


def test_merge_with_light_dedup_removes_boundary_overlap() -> None:
    merged = _merge_with_light_dedup(
        "El paciente refiere dolor abdominal desde ayer.",
        "desde ayer. Niega fiebre.",
    )

    assert merged == "El paciente refiere dolor abdominal desde ayer. Niega fiebre."


def test_normalize_transcript_for_document_removes_inline_noise_tags() -> None:
    normalized = _normalize_transcript_for_document(
        "Paciente refiere dolor [tos] desde ayer.",
    )

    assert normalized == "Paciente refiere dolor desde ayer."


def test_normalize_transcript_for_document_drops_noise_only_chunk() -> None:
    normalized = _normalize_transcript_for_document("[tos]")

    assert normalized == ""


def test_normalize_transcript_for_document_preserves_inaudible() -> None:
    normalized = _normalize_transcript_for_document(
        "Paciente refiere [inaudible] intermitente.",
    )

    assert normalized == "Paciente refiere [inaudible] intermitente."


def test_merge_session_with_existing_document_appends_resumed_transcript() -> None:
    recording_session = SimpleNamespace(
        consolidated_transcript="Paciente refiere cefalea desde ayer.",
    )

    merged = _merge_session_with_existing_document(
        recording_session,
        "Niega fiebre.",
    )

    assert merged == "Paciente refiere cefalea desde ayer.\n\nNiega fiebre."


def test_recording_session_ready_for_consolidation_requires_finish_and_sections() -> None:
    ready_session = SimpleNamespace(
        finished_at=datetime.now(timezone.utc),
        sections=[
            SimpleNamespace(status="transcribed"),
            SimpleNamespace(status="transcribed"),
        ],
    )
    pending_session = SimpleNamespace(
        finished_at=datetime.now(timezone.utc),
        sections=[SimpleNamespace(status="registered")],
    )
    recording_session = SimpleNamespace(
        finished_at=None,
        sections=[SimpleNamespace(status="transcribed")],
    )

    assert is_recording_session_ready_for_consolidation(ready_session) is True
    assert is_recording_session_ready_for_consolidation(pending_session) is False
    assert is_recording_session_ready_for_consolidation(recording_session) is False


class FakeSession:
    def __init__(self) -> None:
        self.statements: list[object] = []
        self.flushed = False
        self.committed = False
        self.added: list[object] = []

    async def execute(self, statement: object) -> FakeResult | None:
        self.statements.append(statement)
        return None

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flushed = True

    async def commit(self) -> None:
        self.committed = True


class FakeResult:
    def __init__(self, value: object | None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> object | None:
        return self.value


@pytest.mark.asyncio
async def test_create_recording_session_reuses_existing_canonical_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing_session = SimpleNamespace(session_id="existing")

    async def fake_get_canonical_recording_session_for_document(*args, **kwargs):
        return existing_session

    monkeypatch.setattr(
        transcription_service,
        "get_canonical_recording_session_for_document",
        fake_get_canonical_recording_session_for_document,
    )

    session = FakeSession()
    encounter = SimpleNamespace(id=11)
    document = SimpleNamespace(id=22, content_markdown="texto existente")

    recording_session = await create_recording_session(
        session,
        encounter=encounter,
        document=document,
        doctor_id=33,
    )

    assert recording_session is existing_session
    assert session.added == []
    assert session.flushed is False


@pytest.mark.asyncio
async def test_create_recording_session_creates_new_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_canonical_recording_session_for_document(*args, **kwargs):
        return None

    monkeypatch.setattr(
        transcription_service,
        "get_canonical_recording_session_for_document",
        fake_get_canonical_recording_session_for_document,
    )

    session = FakeSession()
    encounter = SimpleNamespace(id=11)
    document = SimpleNamespace(id=22, content_markdown="texto existente")

    recording_session = await create_recording_session(
        session,
        encounter=encounter,
        document=document,
        doctor_id=33,
    )

    assert recording_session.document_id == 22
    assert recording_session.encounter_id == 11
    assert recording_session.status == "recording"
    assert len(session.added) == 1
    assert session.flushed is True


@pytest.mark.asyncio
async def test_reset_recording_session_clears_status_and_transcript() -> None:
    document = SimpleNamespace(content_markdown="texto previo", content_json=None)
    encounter = SimpleNamespace(has_been_transcribed=True)
    recording_session = SimpleNamespace(
        id=9,
        status="consolidated",
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        finalized_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        consolidated_transcript="texto previo",
        error_code="boom",
        document=document,
        encounter=encounter,
    )
    session = FakeSession()

    await reset_recording_session(
        session,
        recording_session=recording_session,
        clear_document_content=True,
    )

    assert recording_session.status == "recording"
    assert recording_session.finished_at is None
    assert recording_session.finalized_at is None
    assert recording_session.consolidated_transcript is None
    assert recording_session.error_code is None
    assert encounter.has_been_transcribed is False
    assert document.content_markdown == ""
    assert session.flushed is True


@pytest.mark.asyncio
async def test_register_audio_section_returns_existing_section_on_index_race(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing_section = SimpleNamespace(end_time_ms=28371)
    recording_session = SimpleNamespace(id=33, encounter_id=6)
    execute_calls: list[object] = []

    class IntegritySession:
        def __init__(self) -> None:
            self.flush_calls = 0

        async def execute(self, statement: object) -> FakeResult:
            execute_calls.append(statement)
            if len(execute_calls) == 1:
                return FakeResult(None)
            return FakeResult(existing_section)

        def add(self, _value: object) -> None:
            return None

        async def flush(self) -> None:
            self.flush_calls += 1
            raise transcription_service.IntegrityError("stmt", "params", Exception())

        async def rollback(self) -> None:
            return None

    async def fake_update_encounter_audio_duration(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(
        transcription_service,
        "_update_encounter_audio_duration",
        fake_update_encounter_audio_duration,
    )

    session = IntegritySession()
    section = await register_audio_section(
        session,  # type: ignore[arg-type]
        recording_session=recording_session,  # type: ignore[arg-type]
        client_section_id="client-2",
        section_index=0,
        start_time_ms=16000,
        end_time_ms=28371,
        overlap_ms=0,
        gcs_object_name="gcs",
        content_type="audio/webm",
        byte_size=123,
    )

    assert section is existing_section


def test_transcription_user_message_maps_known_codes() -> None:
    assert "conservó" in transcription_user_message("section_dispatch_failed")
    assert "expiró" in transcription_user_message("audio_expired")


@pytest.mark.asyncio
async def test_reconcile_stuck_sections_marks_needs_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published: list[tuple[int, str]] = []

    async def fake_publish(document_id: int, error_code: str, **kwargs) -> None:
        published.append((document_id, error_code))

    monkeypatch.setattr(
        transcription_service,
        "publish_transcription_error",
        fake_publish,
    )

    stale_time = datetime.now(timezone.utc) - timedelta(
        seconds=STUCK_SECTION_THRESHOLD_SECONDS + 30,
    )
    recording_session = SimpleNamespace(
        status=SESSION_STATUS_FINISHING,
        finished_at=stale_time,
        document_id=42,
        error_code=None,
        sections=[
            SimpleNamespace(
                status=SECTION_STATUS_REGISTERED,
                updated_at=stale_time,
                error_code=None,
                retry_count=0,
            ),
        ],
    )
    session = FakeSession()

    changed = await reconcile_stuck_transcription_sections(
        session,  # type: ignore[arg-type]
        recording_session,  # type: ignore[arg-type]
    )

    assert changed is True
    assert recording_session.status == SESSION_STATUS_NEEDS_REVIEW
    assert recording_session.sections[0].status == SECTION_STATUS_FAILED_FINAL
    assert recording_session.sections[0].error_code == "task_dispatch_exhausted"
    assert session.committed is True
    assert published == [(42, "task_dispatch_exhausted")]


@pytest.mark.asyncio
async def test_reconcile_stuck_sections_ignores_recent_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_publish(document_id: int, error_code: str, **kwargs) -> None:
        raise AssertionError("publish should not be called")

    monkeypatch.setattr(
        transcription_service,
        "publish_transcription_error",
        fake_publish,
    )

    now = datetime.now(timezone.utc)
    recording_session = SimpleNamespace(
        status=SESSION_STATUS_FINISHING,
        finished_at=now,
        document_id=42,
        error_code=None,
        sections=[
            SimpleNamespace(
                status=SECTION_STATUS_TRANSCRIBING,
                updated_at=now,
                error_code=None,
                retry_count=0,
            ),
        ],
    )
    session = FakeSession()

    changed = await reconcile_stuck_transcription_sections(
        session,  # type: ignore[arg-type]
        recording_session,  # type: ignore[arg-type]
        now=now,
    )

    assert changed is False
    assert recording_session.status == SESSION_STATUS_FINISHING


@pytest.mark.asyncio
async def test_reconcile_stuck_sections_uses_shorter_threshold_after_manual_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published: list[tuple[int, str]] = []

    async def fake_publish(document_id: int, error_code: str, **kwargs) -> None:
        published.append((document_id, error_code))

    monkeypatch.setattr(
        transcription_service,
        "publish_transcription_error",
        fake_publish,
    )

    now = datetime.now(timezone.utc)
    stale_time = now - timedelta(
        seconds=STUCK_SECTION_MANUAL_RETRY_THRESHOLD_SECONDS + 15,
    )
    recording_session = SimpleNamespace(
        status=SESSION_STATUS_FINISHING,
        finished_at=stale_time,
        document_id=42,
        error_code=None,
        sections=[
            SimpleNamespace(
                status=SECTION_STATUS_REGISTERED,
                updated_at=stale_time,
                error_code=None,
                retry_count=1,
            ),
        ],
    )
    session = FakeSession()

    changed = await reconcile_stuck_transcription_sections(
        session,  # type: ignore[arg-type]
        recording_session,  # type: ignore[arg-type]
        now=now,
    )

    assert changed is True
    assert recording_session.status == SESSION_STATUS_NEEDS_REVIEW
    assert published == [(42, "task_dispatch_exhausted")]


@pytest.mark.asyncio
async def test_retry_failed_transcription_session_reenqueues_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enqueued: list[str] = []

    def fake_enqueue(section: object, settings: object) -> str:
        enqueued.append(section.section_id)  # type: ignore[attr-defined]
        return "task-name"

    monkeypatch.setattr(
        transcription_service,
        "enqueue_section_task",
        fake_enqueue,
    )

    encounter = SimpleNamespace(audio_expires_at=None)
    recording_session = SimpleNamespace(
        status=SESSION_STATUS_NEEDS_REVIEW,
        encounter_id=7,
        error_code="section_failed_final",
        sections=[
            SimpleNamespace(
                section_id="section-a",
                status=SECTION_STATUS_FAILED_FINAL,
                gcs_object_name="audio/a.webm",
                retry_count=0,
                error_code="task_dispatch_exhausted",
            ),
        ],
    )

    class RetrySession(FakeSession):
        async def execute(self, statement: object) -> FakeResult:
            self.statements.append(statement)
            return FakeResult(encounter)

    session = RetrySession()
    settings = SimpleNamespace()

    success, error_code = await retry_failed_transcription_session(
        session,  # type: ignore[arg-type]
        recording_session,  # type: ignore[arg-type]
        settings=settings,  # type: ignore[arg-type]
    )

    assert success is True
    assert error_code is None
    assert recording_session.status == SESSION_STATUS_FINISHING
    assert recording_session.error_code is None
    assert recording_session.sections[0].status == SECTION_STATUS_REGISTERED
    assert recording_session.sections[0].retry_count == 1
    assert enqueued == ["section-a"]
    assert session.committed is True
