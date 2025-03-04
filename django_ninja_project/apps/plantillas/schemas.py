from ninja import Schema
from typing import Optional


class PlantillaDoctorCreate(Schema):
    """Schema for creating a doctor's template"""

    nombre: str
    tipo_documento: str
    contenido: str
    id_plantilla_base: Optional[int] = None


class PlantillaDoctorResponse(Schema):
    """Schema for doctor's template response"""

    id: int
    nombre: str
    tipo_documento: str
    contenido: Optional[str]
    contenido_base: bool
    id_plantilla_base: Optional[int]
    fecha_creacion: str


class PlantillaDoctorListItem(Schema):
    """Schema for listing doctor's templates with minimal information"""

    id: int
    nombre: str
    tipo_documento: str
