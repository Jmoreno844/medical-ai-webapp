from ninja import Schema
from typing import Dict, Optional, List, Any


class AudioDownloadResponse(Schema):
    success: bool
    audio_uri: Optional[str] = None
    filename: Optional[str] = None
    error: Optional[str] = None


class TranscriptionRequest(Schema):
    id_encuentro: int
    id_documento: int


class TranscriptionResponse(Schema):
    success: bool
    message: Optional[str] = None
    error: Optional[str] = None
