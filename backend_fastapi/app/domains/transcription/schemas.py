from __future__ import annotations

from pydantic import BaseModel


class TranscriptionRequest(BaseModel):
    encounter_id: int
    document_id: int


class TranscriptionResponse(BaseModel):
    success: bool
    message: str | None = None
    error: str | None = None
