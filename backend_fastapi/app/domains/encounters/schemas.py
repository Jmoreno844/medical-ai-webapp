from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class EmptyPayload(BaseModel):
    pass


class EncounterListItem(BaseModel):
    id: int
    doctor_id: int
    patient_id: int | None
    patient_connected: bool | None
    encounter_name: str | None
    occurred_at: datetime


class EncounterDetail(EncounterListItem):
    has_been_transcribed: bool


class EncounterUpdate(BaseModel):
    patient_id: int | None = None
    patient_connected: bool | None = None
    encounter_name: str | None = None
    occurred_at: datetime | None = None
    has_been_transcribed: bool | None = None


class EmptyEncounterResponse(BaseModel):
    id: int


class AudioUploadRequest(BaseModel):
    audio_duration_seconds: int = 0


class AudioUploadResponse(BaseModel):
    success: bool
    upload_url: str | None = None
    filename: str | None = None
    error: str | None = None


class AudioExistsResponse(BaseModel):
    exists: bool
    duration: int = 0
    has_been_transcribed: bool
    expires_at: datetime | None = None
    is_expired: bool = False

