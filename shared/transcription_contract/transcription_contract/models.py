from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Speaker(str, Enum):
    MEDICO = "MEDICO"
    PACIENTE = "PACIENTE"
    ACOMPANANTE = "ACOMPANANTE"
    DESCONOCIDO = "DESCONOCIDO"


SpeakerLiteral = Literal["MEDICO", "PACIENTE", "ACOMPANANTE", "DESCONOCIDO"]


class TranscriptionTurn(BaseModel):
    speaker: SpeakerLiteral
    text: str
    overlaps_previous: bool = False
    overlaps_next: bool = False


class ChunkTranscript(BaseModel):
    chunk_id: str
    start_ms: int
    end_ms: int
    turns: list[TranscriptionTurn] = Field(default_factory=list)


class ConsultationTranscript(BaseModel):
    session_id: str
    chunks: list[ChunkTranscript] = Field(default_factory=list)
