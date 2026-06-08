from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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


class ClinicalExtractionResultRequest(BaseModel):
    status: str
    facts: dict[str, Any] | None = None
    raw_model_output: dict[str, Any] | None = None
    extraction_model: str | None = None
    grounding_stats: dict[str, Any] | None = None
    error_code: str | None = None
    latency_ms: int | None = None
