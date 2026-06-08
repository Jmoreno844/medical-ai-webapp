from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users_user"

    id: Mapped[int] = mapped_column(primary_key=True)
    password: Mapped[str] = mapped_column(String(128))
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_superuser: Mapped[bool] = mapped_column(Boolean)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(50))
    last_name: Mapped[str] = mapped_column(String(50))
    role: Mapped[str] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean)
    clinical_access_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_staff: Mapped[bool] = mapped_column(Boolean)
    date_joined: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Encounter(Base):
    __tablename__ = "encounters_encounter"

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users_user.id"))
    patient_id: Mapped[int | None] = mapped_column(ForeignKey("patients_patient.id"))
    patient_connected: Mapped[bool] = mapped_column(Boolean)
    encounter_name: Mapped[str | None] = mapped_column(String(255))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    audio_file_name: Mapped[str | None] = mapped_column(String(255))
    audio_uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    audio_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    audio_duration_seconds: Mapped[int | None] = mapped_column(Integer)
    has_been_transcribed: Mapped[bool] = mapped_column(Boolean)

    doctor: Mapped[User] = relationship()
    patient: Mapped["Patient | None"] = relationship()
    documents: Mapped[list["Document"]] = relationship(back_populates="encounter")
    transcription_recording_sessions: Mapped[list["TranscriptionRecordingSession"]] = (
        relationship(back_populates="encounter")
    )


class Document(Base):
    __tablename__ = "documents_document"

    id: Mapped[int] = mapped_column(primary_key=True)
    encounter_id: Mapped[int] = mapped_column(ForeignKey("encounters_encounter.id"))
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users_user.id"))
    doctor_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("templates_doctortemplate.id")
    )
    kind: Mapped[str] = mapped_column(String(20))
    content_markdown: Mapped[str] = mapped_column(Text)
    content_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_on: Mapped[date] = mapped_column(Date)

    doctor: Mapped[User] = relationship()
    encounter: Mapped[Encounter] = relationship(back_populates="documents")
    doctor_template: Mapped["DoctorTemplate | None"] = relationship()
    transcription_recording_sessions: Mapped[list["TranscriptionRecordingSession"]] = (
        relationship(back_populates="document")
    )


class TranscriptionRecordingSession(Base):
    __tablename__ = "transcription_recording_session"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    encounter_id: Mapped[int] = mapped_column(ForeignKey("encounters_encounter.id"))
    document_id: Mapped[int] = mapped_column(ForeignKey("documents_document.id"))
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users_user.id"))
    status: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consolidated_transcript: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(64))

    encounter: Mapped[Encounter] = relationship(
        back_populates="transcription_recording_sessions"
    )
    document: Mapped[Document] = relationship(
        back_populates="transcription_recording_sessions"
    )
    doctor: Mapped[User] = relationship()
    sections: Mapped[list["TranscriptionAudioSection"]] = relationship(
        back_populates="recording_session",
        order_by="TranscriptionAudioSection.section_index",
    )


class TranscriptionAudioSection(Base):
    __tablename__ = "transcription_audio_section"
    __table_args__ = (
        UniqueConstraint(
            "recording_session_id",
            "client_section_id",
            name="uq_transcription_section_client_id",
        ),
        UniqueConstraint(
            "recording_session_id",
            "section_index",
            name="uq_transcription_section_index",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    section_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    recording_session_id: Mapped[int] = mapped_column(
        ForeignKey("transcription_recording_session.id")
    )
    client_section_id: Mapped[str] = mapped_column(String(64))
    section_index: Mapped[int] = mapped_column(Integer)
    start_time_ms: Mapped[int] = mapped_column(Integer)
    end_time_ms: Mapped[int] = mapped_column(Integer)
    overlap_ms: Mapped[int] = mapped_column(Integer)
    gcs_object_name: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(100))
    byte_size: Mapped[int | None] = mapped_column(Integer)
    original_gcs_object_name: Mapped[str | None] = mapped_column(String(512))
    original_content_type: Mapped[str | None] = mapped_column(String(100))
    original_byte_size: Mapped[int | None] = mapped_column(Integer)
    clipped_gcs_object_name: Mapped[str | None] = mapped_column(String(512))
    clipped_content_type: Mapped[str | None] = mapped_column(String(100))
    clipped_byte_size: Mapped[int | None] = mapped_column(Integer)
    transcription_source_gcs_object_name: Mapped[str | None] = mapped_column(
        String(512)
    )
    frontend_vad_metadata_json: Mapped[str | None] = mapped_column(Text)
    transcription_source: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    raw_transcript: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(64))
    retry_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    recording_session: Mapped[TranscriptionRecordingSession] = relationship(
        back_populates="sections"
    )


class Patient(Base):
    __tablename__ = "patients_patient"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PatientDoctor(Base):
    __tablename__ = "patients_patientdoctor"

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users_user.id"))
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients_patient.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    doctor: Mapped[User] = relationship()
    patient: Mapped[Patient] = relationship()


class BaseTemplate(Base):
    __tablename__ = "templates_basetemplate"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    document_kind: Mapped[str] = mapped_column(String(50))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DoctorTemplate(Base):
    __tablename__ = "templates_doctortemplate"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    document_kind: Mapped[str] = mapped_column(String(50))
    uses_base_content: Mapped[bool] = mapped_column(Boolean)
    base_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("templates_basetemplate.id")
    )
    content: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users_user.id"))

    doctor: Mapped[User] = relationship()
    base_template: Mapped[BaseTemplate | None] = relationship()


class TemplateUsage(Base):
    __tablename__ = "templates_templateusage"

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_template_id: Mapped[int] = mapped_column(
        ForeignKey("templates_doctortemplate.id")
    )
    use_count: Mapped[int] = mapped_column(Integer)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users_user.id"))

    doctor_template: Mapped[DoctorTemplate] = relationship()
    doctor: Mapped[User] = relationship()


class RevokedToken(Base):
    __tablename__ = "fastapi_revoked_token"

    id: Mapped[int] = mapped_column(primary_key=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditUserSession(Base):
    __tablename__ = "audit_user_session"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str | None] = mapped_column(String(64), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users_user.id"), index=True)
    ip_hmac: Mapped[str] = mapped_column(String(64), index=True)
    network_prefix: Mapped[str | None] = mapped_column(String(80))
    ip_encrypted: Mapped[str | None] = mapped_column(Text)
    user_agent_summary: Mapped[str | None] = mapped_column(String(150))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User | None] = relationship()


class AuditEvent(Base):
    __tablename__ = "audit_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[str | None] = mapped_column(String(64), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users_user.id"), index=True)
    actor_type: Mapped[str] = mapped_column(String(32))
    actor_role_snapshot: Mapped[str | None] = mapped_column(String(64))
    actor_name_snapshot: Mapped[str | None] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(80), index=True)
    result: Mapped[str] = mapped_column(String(20), index=True)
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("audit_user_session.id"),
        index=True,
    )
    patient_id: Mapped[int | None] = mapped_column(
        ForeignKey("patients_patient.id"),
        index=True,
    )
    encounter_id: Mapped[int | None] = mapped_column(
        ForeignKey("encounters_encounter.id"),
        index=True,
    )
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents_document.id"),
        index=True,
    )
    resource_type: Mapped[str | None] = mapped_column(String(64))
    resource_id: Mapped[str | None] = mapped_column(String(64))
    service_name: Mapped[str | None] = mapped_column(String(128))
    service_account: Mapped[str | None] = mapped_column(String(255))
    error_code: Mapped[str | None] = mapped_column(String(64))
    trace_id: Mapped[str | None] = mapped_column(String(32), index=True)
    request_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    actor: Mapped[User | None] = relationship(foreign_keys=[actor_id])
    audit_session: Mapped[AuditUserSession | None] = relationship()
    patient: Mapped[Patient | None] = relationship()
    encounter: Mapped[Encounter | None] = relationship()
    document: Mapped[Document | None] = relationship()


class CopilotRun(Base):
    __tablename__ = "copilot_copilotrun"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True)
    thread_id: Mapped[str] = mapped_column(String(255))
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users_user.id"))
    encounter_id: Mapped[int] = mapped_column(ForeignKey("encounters_encounter.id"))
    status: Mapped[str] = mapped_column(String(32))
    intent: Mapped[str | None] = mapped_column(String(64))
    requires_human_review: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    doctor: Mapped[User] = relationship()
    encounter: Mapped[Encounter] = relationship()
    patch_sets: Mapped[list["CopilotPatchSet"]] = relationship(back_populates="run")
    patches: Mapped[list["CopilotPatch"]] = relationship(back_populates="run")


class CopilotPatchSet(Base):
    __tablename__ = "copilot_copilotpatchset"

    id: Mapped[int] = mapped_column(primary_key=True)
    patch_set_id: Mapped[str] = mapped_column(String(64), unique=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("copilot_copilotrun.id"))
    encounter_id: Mapped[int] = mapped_column(ForeignKey("encounters_encounter.id"))
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users_user.id"))
    target_document_id: Mapped[int] = mapped_column(ForeignKey("documents_document.id"))
    base_version: Mapped[int] = mapped_column(Integer)
    base_hash: Mapped[str] = mapped_column(String(128))
    rationale: Mapped[str | None] = mapped_column(Text)
    source_context_document_ids: Mapped[list[str]] = mapped_column(JSONB)
    target_document_title: Mapped[str | None] = mapped_column(String(255))
    target_selection_reason: Mapped[str | None] = mapped_column(Text)
    document_preview_after: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32))
    edit_scope: Mapped[str | None] = mapped_column(String(32))
    clinical_impact_level: Mapped[str | None] = mapped_column(String(32))
    affected_sections: Mapped[list[str]] = mapped_column(JSONB)
    review_comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    run: Mapped[CopilotRun] = relationship(back_populates="patch_sets")
    encounter: Mapped[Encounter] = relationship()
    doctor: Mapped[User] = relationship()
    target_document: Mapped[Document] = relationship()
    patches: Mapped[list["CopilotPatch"]] = relationship(back_populates="patch_set")


class CopilotPatch(Base):
    __tablename__ = "copilot_copilotpatch"

    id: Mapped[int] = mapped_column(primary_key=True)
    patch_id: Mapped[str] = mapped_column(String(64), unique=True)
    patch_set_id: Mapped[int | None] = mapped_column(
        ForeignKey("copilot_copilotpatchset.id")
    )
    run_id: Mapped[int] = mapped_column(ForeignKey("copilot_copilotrun.id"))
    encounter_id: Mapped[int] = mapped_column(ForeignKey("encounters_encounter.id"))
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users_user.id"))
    target_document_id: Mapped[int] = mapped_column(ForeignKey("documents_document.id"))
    base_version: Mapped[int] = mapped_column(Integer)
    order_index: Mapped[int] = mapped_column(Integer)
    patch_type: Mapped[str] = mapped_column(String(64))
    operation_type: Mapped[str] = mapped_column(String(64))
    anchor: Mapped[dict[str, Any]] = mapped_column(JSONB)
    expected_hash: Mapped[str | None] = mapped_column(String(128))
    replacement_text: Mapped[str | None] = mapped_column(Text)
    inserted_text: Mapped[str | None] = mapped_column(Text)
    old_text: Mapped[str | None] = mapped_column(Text)
    new_text: Mapped[str | None] = mapped_column(Text)
    resolved_start: Mapped[int | None] = mapped_column(Integer)
    resolved_end: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[float | None] = mapped_column(Float)
    conflict_reason: Mapped[str | None] = mapped_column(Text)
    document_preview_after: Mapped[str | None] = mapped_column(Text)
    content_preview: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str | None] = mapped_column(Text)
    source_context_document_ids: Mapped[list[str]] = mapped_column(JSONB)
    target_document_title: Mapped[str | None] = mapped_column(String(255))
    target_selection_reason: Mapped[str | None] = mapped_column(Text)
    section: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32))
    review_comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    patch_set: Mapped[CopilotPatchSet | None] = relationship(back_populates="patches")
    run: Mapped[CopilotRun] = relationship(back_populates="patches")
    encounter: Mapped[Encounter] = relationship()
    doctor: Mapped[User] = relationship()
    target_document: Mapped[Document] = relationship()
