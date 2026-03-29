from ninja import Schema
from typing import Optional


class PatientCreate(Schema):
    name: str
    summary: Optional[str] = None


class PatientResponse(Schema):
    id: int
    name: str
    summary: Optional[str] = None


class PatientUpdate(Schema):
    name: str
    summary: Optional[str] = None
