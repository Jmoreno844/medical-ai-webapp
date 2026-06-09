from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ClinicalExtractionChunk(BaseModel):
    chunk_id: str
    section_index: int
    speaker: str | None = None
    text: str
    start_time_ms: int | None = None
    end_time_ms: int | None = None


class ClinicalExtractionWorkItemResponse(BaseModel):
    session_id: str
    encounter_id: int
    document_id: int
    doctor_id: int
    language: str | None = None
    chunks: list[ClinicalExtractionChunk] = Field(default_factory=list)
    callback_token: str


class ClinicalExtractionEvidenceResult(BaseModel):
    fact_path: str
    quote: str
    supports_fields: list[str] = Field(default_factory=list)
    chunk_hint: str | None = None
    matched: bool = False
    match_score: float | None = None
    matched_chunk_ids: list[str] = Field(default_factory=list)
    uttered_by_role: str | None = None
    ambiguous: bool = False
    speaker_mismatch: bool = False


class DebugClinicalMentionEvidenceResult(BaseModel):
    fact_path: str
    quote: str
    turn_id: str | None = None
    matched: bool = False
    match_score: float | None = None
    matched_chunk_ids: list[str] = Field(default_factory=list)
    uttered_by_role: str | None = None
    ambiguous: bool = False
    speaker_mismatch: bool = False


class ClinicalExtractionResultRequest(BaseModel):
    status: str
    facts: dict[str, Any] | None = None
    raw_model_output: dict[str, Any] | None = None
    extraction_model: str | None = None
    grounding_stats: dict[str, Any] | None = None
    error_code: str | None = None
    latency_ms: int | None = None


class DebugClinicalExtractionContext(BaseModel):
    encounter_id: int = 0
    document_id: int = 0
    doctor_id: int = 0
    patient_id: int | None = None
    patient_name: str | None = None
    occurred_at: datetime | None = None


class DebugClinicalExtractionRequest(BaseModel):
    session_id: str | None = None
    transcript_json: dict[str, Any] | None = None
    language: str | None = None
    provider: str | None = None
    model: str | None = None
    context: DebugClinicalExtractionContext | None = None

    @model_validator(mode="after")
    def validate_input_source(self) -> "DebugClinicalExtractionRequest":
        has_session = bool(self.session_id)
        has_transcript = self.transcript_json is not None
        if has_session == has_transcript:
            raise ValueError("Provide exactly one of session_id or transcript_json")
        return self


class DebugClinicalExtractionSessionTranscriptResponse(BaseModel):
    session_id: str
    encounter_id: int
    document_id: int
    doctor_id: int
    status: str
    transcript_json: dict[str, Any]


class DebugClinicalExtractionResponse(BaseModel):
    session_id: str
    chunks: list[ClinicalExtractionChunk]
    raw_mentions: dict[str, Any] | None = None
    processed_mentions: dict[str, Any] | None = None
    evidence: list[DebugClinicalMentionEvidenceResult] = Field(default_factory=list)
    grounding_stats: dict[str, Any] = Field(default_factory=dict)
    extraction_model: str | None = None
    latency_ms: int | None = None
    status: str
    error_code: str | None = None
