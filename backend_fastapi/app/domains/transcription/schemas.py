from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class TranscriptionRequest(BaseModel):
    encounter_id: int
    document_id: int


class TranscriptionResponse(BaseModel):
    success: bool
    message: str | None = None
    error: str | None = None


class RecordingSessionCreate(BaseModel):
    encounter_id: int
    document_id: int


class RecordingSessionResponse(BaseModel):
    success: bool
    session_id: str | None = None
    status: str | None = None
    error: str | None = None


class SectionUploadUrlRequest(BaseModel):
    client_section_id: str
    section_index: int
    content_type: str = "audio/webm;codecs=opus"


class SectionUploadUrlResponse(BaseModel):
    success: bool
    upload_url: str | None = None
    gcs_object_name: str | None = None
    error: str | None = None


class AudioSectionRegisterRequest(BaseModel):
    client_section_id: str
    section_index: int
    start_time_ms: int
    end_time_ms: int
    overlap_ms: int = 0
    gcs_object_name: str
    content_type: str = "audio/webm"
    byte_size: int | None = None


class AudioSectionResponse(BaseModel):
    section_id: str
    client_section_id: str
    section_index: int
    start_time_ms: int
    end_time_ms: int
    overlap_ms: int
    gcs_object_name: str
    content_type: str
    byte_size: int | None
    status: str
    raw_transcript: str | None = None
    error_code: str | None = None
    retry_count: int
    created_at: datetime
    updated_at: datetime


class AudioSectionRegisterResponse(BaseModel):
    success: bool
    section: AudioSectionResponse | None = None
    error: str | None = None


class RecordingSessionStatusResponse(BaseModel):
    success: bool
    session_id: str
    encounter_id: int
    document_id: int
    status: str
    started_at: datetime
    finished_at: datetime | None
    finalized_at: datetime | None
    consolidated_transcript: str | None
    error_code: str | None
    sections: list[AudioSectionResponse]


class RecordingSessionFinishResponse(BaseModel):
    success: bool
    status: str | None = None
    error: str | None = None
