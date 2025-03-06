from pydantic import BaseModel
from typing import Dict, Optional, List, Any


class TranscriptionResponse(BaseModel):
    """Response schema for transcription results"""

    success: bool
    message: str
    data: Optional[Dict] = None
    transcript: Optional[str] = None
    format: Optional[str] = None
    model: Optional[str] = None


class GeminiResponse(BaseModel):
    """Response schema for Gemini API results"""

    success: bool
    message: str
    contenido: Optional[str] = None


class DocumentTranscriptionResponse(BaseModel):
    """Response schema for document transcription results"""

    success: bool
    message: str
    document_id: int
    transcript_length: int = 0


class ErrorResponse(BaseModel):
    """Schema for error responses"""

    detail: str


# Input schemas for validation
class TranscriptionFormat(BaseModel):
    """Input schema for specifying transcription format"""

    format: str = "speakers"

    class Config:
        schema_extra = {"example": {"format": "speakers"}}
