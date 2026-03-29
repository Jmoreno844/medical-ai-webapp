from ninja import Schema
from typing import Optional


class PacienteCreate(Schema):
    nombre: str
    resumen: Optional[str] = None


class PacienteResponse(Schema):
    id: int
    nombre: str
    resumen: Optional[str] = None


class PacienteUpdate(Schema):
    nombre: str
    resumen: Optional[str] = None
