from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domains.audit.schemas import AuditEventOut
from app.domains.auth.roles import normalize_user_role


class AdminUserListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    last_name: str
    role: str
    is_active: bool
    last_login: datetime | None
    date_joined: datetime
    active_session_count: int = 0
    last_session_started_at: datetime | None = None
    login_success_24h: int = 0
    login_failure_24h: int = 0

    @field_validator("role", mode="before")
    @classmethod
    def _normalize_role(cls, value: str) -> str:
        return normalize_user_role(value)


class AdminUserListOut(BaseModel):
    items: list[AdminUserListItem]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)


class AdminUserSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: int | None
    ip_hmac: str
    network_prefix: str | None
    user_agent_summary: str | None
    started_at: datetime
    last_seen_at: datetime
    ended_at: datetime | None


class AdminUserDetailOut(BaseModel):
    user: AdminUserListItem
    sessions: list[AdminUserSessionOut]
    recent_events: list[AuditEventOut]


class AdminUserStatusUpdate(BaseModel):
    is_active: bool
