from __future__ import annotations

from datetime import datetime
from typing import Any

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
    content_type_original: str = "audio/webm;codecs=opus"
    content_type_clipped: str = "audio/ogg;codecs=opus"


class SignedAudioArtifactResponse(BaseModel):
    upload_url: str
    gcs_object_name: str
    content_type: str


class SectionUploadUrlResponse(BaseModel):
    success: bool
    original: SignedAudioArtifactResponse | None = None
    clipped: SignedAudioArtifactResponse | None = None
    error: str | None = None


class AudioSectionRegisterRequest(BaseModel):
    client_section_id: str
    section_index: int
    start_time_ms: int
    end_time_ms: int
    overlap_ms: int = 0
    original_gcs_object_name: str
    original_content_type: str = "audio/webm"
    original_byte_size: int | None = None
    clipped_gcs_object_name: str
    clipped_content_type: str = "audio/ogg"
    clipped_byte_size: int | None = None
    transcription_source_gcs_object_name: str
    frontend_vad_metadata: dict[str, Any] | None = None


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
    original_gcs_object_name: str | None = None
    original_content_type: str | None = None
    original_byte_size: int | None = None
    clipped_gcs_object_name: str | None = None
    clipped_content_type: str | None = None
    clipped_byte_size: int | None = None
    transcription_source_gcs_object_name: str | None = None
    frontend_vad_metadata: dict[str, Any] | None = None
    transcription_source: str | None = None
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


class RecordingSessionRetryResponse(BaseModel):
    success: bool
    status: str | None = None
    error: str | None = None
    error_code: str | None = None


class SectionWorkItemResponse(BaseModel):
    section_id: str
    session_id: str
    encounter_id: int
    document_id: int
    section_index: int
    original_gcs_object_name: str | None = None
    original_gcs_uri: str | None = None
    original_content_type: str | None = None
    clipped_gcs_object_name: str | None = None
    clipped_gcs_uri: str | None = None
    clipped_content_type: str | None = None
    transcription_source_gcs_object_name: str
    transcription_source_gcs_uri: str
    transcription_source_content_type: str


class SectionResultRequest(BaseModel):
    status: str
    transcript: str | None = None
    error_code: str | None = None
    vad_decision: str | None = None
    vad_speech_ms: int | None = None
    vad_speech_ratio: float | None = None
    vad_error_code: str | None = None
    gemini_model: str | None = None
    gemini_latency_ms: int | None = None
    worker_latency_ms: int | None = None
    transcription_source: str | None = None


class DebugSpeechIntervalResponse(BaseModel):
    start_ms: int
    end_ms: int


class DebugFrontendCutResponse(BaseModel):
    section_duration_ms: int
    speech_duration_ms: int
    speech_frame_count: int
    has_detected_speech: bool
    cut_reason: str
    overlap_ms: int
    speech_intervals: list[DebugSpeechIntervalResponse]
    removable_silences: list[DebugSpeechIntervalResponse]
    retained_intervals: list[DebugSpeechIntervalResponse]


class DebugWorkerCutResponse(BaseModel):
    original_duration_ms: int
    retained_duration_ms: int
    speech_duration_ms: int
    speech_ratio: float
    retained_intervals: list[DebugSpeechIntervalResponse]
    removable_silences: list[DebugSpeechIntervalResponse]
    speech_intervals: list[DebugSpeechIntervalResponse]
    trim_applied: bool


class DebugWorkerInputResponse(BaseModel):
    input_byte_size: int
    decoded_sample_count: int
    decoded_duration_ms: int
    sample_rate_hz: int
    trimmed_audio_byte_size: int


class DebugCutComparisonResponse(BaseModel):
    original_duration_ms: int
    frontend_retained_duration_ms: int
    worker_retained_duration_ms: int
    retained_duration_delta_ms: int
    frontend_removed_silence_ms: int
    worker_removed_silence_ms: int
    silence_removed_delta_ms: int


class DebugTranscriptionBridgeResponse(BaseModel):
    success: bool
    mode: str = "transcribe"
    provider: str
    model: str
    transcript: str
    content_type: str
    vad_decision: str
    vad_speech_ms: int
    vad_speech_ratio: float
    vad_error_code: str | None = None
    frontend_cut: DebugFrontendCutResponse
    worker_input: DebugWorkerInputResponse
    worker_cut: DebugWorkerCutResponse
    comparison: DebugCutComparisonResponse
