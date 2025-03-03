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
    id_paciente: Optional[int]
    paciente_conectado: Optional[bool]
    nombre_encuentro: Optional[str]
    fecha: Optional[datetime] = None

    class Config:
        exclude_unset = True


class EmptyEncuentroResponse(Schema):
    id: int
