from typing import Optional, List
from ninja import Schema
from datetime import date
from pydantic import BaseModel


class DocumentoIn(Schema):
    id_encuentro: int
    tipo: str
    id_plantilla_doctor: Optional[int] = None
    contenido: Optional[str] = ""  # Make contenido optional with empty string default


class DocumentoOut(Schema):
    id: int
    id_encuentro: int
    tipo: str
    id_plantilla_doctor: Optional[int]
    contenido: str
    fecha_creacion: date
    id_medico: int


class DocumentoUpdateIn(Schema):
    """Schema for updating only the content of an existing document"""

    contenido: str


class DocumentoContentOut(Schema):
    """Schema for returning only the content of a document"""

    contenido: str


class SuccessResponse(Schema):
    """Generic success response with message"""

    success: bool
    message: str


class TranscriptionNotificationIn(BaseModel):
    id_documento: int  # Changed from documento_id
    status: str = "complete"
    message: str = None


class SSETokenResponse(Schema):
    """Response for SSE token generation"""

    success: bool
    token: Optional[str] = None
    error: Optional[str] = None


class DocumentGenerationRequest(Schema):
    documento_id: int
    generation_type: str  # "summarize", "expand", "translate", etc.
    content: Optional[str] = None  # Optional content to use instead of document content
    prompt: Optional[str] = None  # Optional custom prompt


class DocumentGenerationResponse(Schema):
    success: bool
    processing_id: str = None
    sse_token: str = None
    documento_id: int = None
    message: str = None
    error: str = None


class GenerationChunkIn(Schema):
    id_documento: int  # Changed from document_id
    id_proceso: str  # Changed from processing_id
    chunk: Optional[str] = None
    is_complete: bool = False
    is_error: bool = False
    error: Optional[str] = None


class DocumentGenerationWorkflowRequest(Schema):
    """Schema for requesting document generation workflow"""

    id_documento_contexto: int
    id_documento_transcripcion: int
    id_plantilla_doctor: int
    id_documento_nuevo: int


class DocumentGenerationWorkflowResponse(Schema):
    """Response for document generation workflow"""

    success: bool
    id_proceso: Optional[str] = None
    sse_token: Optional[str] = None
    id_documento_nuevo: Optional[int] = None
    message: Optional[str] = None
    error: Optional[str] = None
