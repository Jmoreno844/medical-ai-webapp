from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
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
