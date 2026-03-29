from ninja import Schema
from typing import Optional


class DoctorTemplateCreate(Schema):
    name: str
    document_kind: str
    content: str
    base_template_id: Optional[int] = None


class DoctorTemplateResponse(Schema):
    id: int
    name: str
    document_kind: str
    content: Optional[str]
    uses_base_content: bool
    base_template_id: Optional[int]


class DoctorTemplateListItem(Schema):
    id: int
    name: str
    document_kind: str
    use_count: Optional[int] = 0
    last_used_at: Optional[str] = None
    is_base: bool
    created_at: Optional[str] = None


class DoctorTemplateUpdate(Schema):
    name: str
    document_kind: str
    content: str
