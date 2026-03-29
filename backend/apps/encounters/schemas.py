from ninja import Schema
from datetime import datetime
from typing import Optional


class EncounterCreate(Schema):
    doctor_id: int
    encounter_name: Optional[str]
    occurred_at: datetime


class EncountersListOut(Schema):
    id: int
    doctor_id: int
    patient_id: Optional[int]
    patient_connected: Optional[bool]
    encounter_name: str
    occurred_at: datetime


class EncounterDetailOut(Schema):
    id: int
    doctor_id: int
    patient_id: Optional[int]
    patient_connected: Optional[bool]
    encounter_name: str
    occurred_at: datetime
    has_been_transcribed: bool


class EncounterUpdate(Schema):
    patient_id: Optional[int] = None
    patient_connected: Optional[bool] = None
    encounter_name: Optional[str] = None
    occurred_at: Optional[datetime] = None
    has_been_transcribed: Optional[bool] = None

    class Config:
        exclude_unset = True
        arbitrary_types_allowed = True


class EmptyPayload(Schema):
    pass


class EmptyEncounterResponse(Schema):
    id: int


class AudioUploadRequest(Schema):
    audio_duration_seconds: int = 0


class AudioUploadResponse(Schema):
    success: bool
    upload_url: Optional[str] = None
    filename: Optional[str] = None
    error: Optional[str] = None


class AudioExistsResponse(Schema):
    exists: bool
    duration: int = 0
    has_been_transcribed: bool
