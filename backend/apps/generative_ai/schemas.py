from ninja import Schema
from typing import Dict, Optional, List, Any


class AudioDownloadResponse(Schema):
    success: bool
    audio_uri: Optional[str] = None
    filename: Optional[str] = None
    error: Optional[str] = None


class TranscriptionRequest(Schema):
    encounter_id: int
    document_id: int


class TranscriptionResponse(Schema):
    success: bool
    message: Optional[str] = None
    error: Optional[str] = None
