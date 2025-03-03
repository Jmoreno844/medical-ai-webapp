from ninja import Schema
from datetime import date
from typing import Optional


class EncuentroCreate(Schema):
    id_medico: int
    nombre_encuentro: Optional[str]
    fecha: date


class EncuentroOut(Schema):
    id: int
    id_medico: int
    id_paciente: Optional[int]
    nombre_encuentro: str
    fecha: date


class EncuentroUpdate(Schema):
    id_paciente: Optional[int]
    nombre_encuentro: Optional[str]
    fecha: Optional[date]


class EmptyEncuentroResponse(Schema):
    id: int
