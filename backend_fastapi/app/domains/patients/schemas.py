from pydantic import BaseModel


class PatientCreate(BaseModel):
    name: str
    summary: str | None = None


class PatientUpdate(BaseModel):
    name: str
    summary: str | None = None


class PatientResponse(BaseModel):
    id: int
    name: str
    summary: str | None = None

