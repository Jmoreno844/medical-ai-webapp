from pydantic import BaseModel


class DoctorTemplateCreate(BaseModel):
    name: str
    document_kind: str
    content: str
    base_template_id: int | None = None


class DoctorTemplateUpdate(BaseModel):
    name: str
    document_kind: str
    content: str


class DoctorTemplateResponse(BaseModel):
    id: int
    name: str
    document_kind: str
    content: str | None
    uses_base_content: bool
    base_template_id: int | None


class DoctorTemplateListItem(BaseModel):
    id: int
    name: str
    document_kind: str
    use_count: int | None = 0
    last_used_at: str | None = None
    is_base: bool
    created_at: str | None = None

