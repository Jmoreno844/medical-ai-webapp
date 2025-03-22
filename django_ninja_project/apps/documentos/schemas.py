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
    documento_id: int
    status: str = "complete"
    message: str = None


class SSETokenResponse(Schema):
    """Response for SSE token generation"""

    success: bool
    token: Optional[str] = None
    error: Optional[str] = None
