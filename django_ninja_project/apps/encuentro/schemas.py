from ninja import Schema
from datetime import datetime  # Changed from date to datetime
from typing import Optional


class EncuentroCreate(Schema):
    id_medico: int
    nombre_encuentro: Optional[str]
    fecha: datetime  # Changed from date to datetime


class EncuentroOut(Schema):
    id: int
    id_medico: int
    id_paciente: Optional[int]
    paciente_conectado: Optional[bool]
    nombre_encuentro: str
    fecha: datetime  # Changed from date to datetime


class EncuentroUpdate(Schema):
    id_paciente: Optional[int] = None
    paciente_conectado: Optional[bool] = None
    nombre_encuentro: Optional[str] = None
    fecha: Optional[datetime] = None

    class Config:
        exclude_unset = True
        arbitrary_types_allowed = True


class EmptyEncuentroResponse(Schema):
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
