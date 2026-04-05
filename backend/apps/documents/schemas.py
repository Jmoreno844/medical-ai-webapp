from typing import Optional
from ninja import Schema
from datetime import date
from pydantic import BaseModel


class DocumentCreateIn(Schema):
    encounter_id: int
    kind: str
    doctor_template_id: Optional[int] = None
    content: Optional[str] = ""


class DocumentOut(Schema):
    id: int
    encounter_id: int
    kind: str
    doctor_template_id: Optional[int]
    doctor_template_name: Optional[str] = None
    content: str
    created_on: date
    doctor_id: int


class DocumentContentUpdateIn(Schema):
    content: str


class DocumentContentOut(Schema):
    content: str


class SuccessResponse(Schema):
    success: bool
    message: str


class TranscriptionNotificationIn(BaseModel):
    document_id: int
    status: str = "complete"
    message: str = None


class SSETokenResponse(Schema):
    success: bool
    token: Optional[str] = None
    error: Optional[str] = None


class DocumentGenerationRequest(Schema):
    document_id: int
    generation_type: str
    content: Optional[str] = None
    prompt: Optional[str] = None


class DocumentGenerationResponse(Schema):
    success: bool
    processing_id: str = None
    sse_token: str = None
    document_id: int = None
    message: str = None
    error: str = None


class GenerationChunkIn(Schema):
    document_id: int
    process_id: str
    chunk: Optional[str] = None
    is_complete: bool = False
    is_error: bool = False
    error: Optional[str] = None


class DocumentGenerationWorkflowRequest(Schema):
    context_document_id: int
    transcription_document_id: int
    doctor_template_id: int
    new_document_id: int


class DocumentGenerationWorkflowResponse(Schema):
    success: bool
    process_id: Optional[str] = None
    sse_token: Optional[str] = None
    new_document_id: Optional[int] = None
    message: Optional[str] = None
    error: Optional[str] = None
