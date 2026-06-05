from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


CLIENT_AUDIT_ACTIONS = frozenset(
    {
        "document.copied",
        "document.downloaded",
        "document.exported",
    }
)


class AuditClientEventIn(BaseModel):
    action: str
    patient_id: int | None = None
    encounter_id: int | None = None
    document_id: int | None = None


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: str | None
    actor_id: int | None
    actor_type: str
    actor_role_snapshot: str | None
    actor_name_snapshot: str | None
    action: str
    result: str
    session_id: str | None
    patient_id: int | None
    encounter_id: int | None
    document_id: int | None
    resource_type: str | None
    resource_id: str | None
    service_name: str | None
    service_account: str | None
    error_code: str | None
    trace_id: str | None
    request_id: str | None
    created_at: datetime


class AuditEventListOut(BaseModel):
    items: list[AuditEventOut]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)
