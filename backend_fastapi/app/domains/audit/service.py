from __future__ import annotations

import hashlib
import hmac
import ipaddress
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from cryptography.fernet import Fernet
from fastapi import HTTPException, Request, status
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models import AuditEvent, AuditUserSession, User
from app.domains.auth.roles import is_admin_role, normalize_user_role

HIGH_VALUE_IP_ACTIONS = frozenset(
    {
        "auth.login_success",
        "auth.login_failure",
        "auth.logout",
        "auth.password_recovery_requested",
        "clinical.access_denied",
        "document.downloaded",
        "document.exported",
        "support.customer_data_accessed",
        "audit.audit_log_viewed",
        "user.created",
        "user.deactivated",
        "user.role_changed",
    }
)


@dataclass(slots=True)
class AuditActor:
    actor_id: int | None
    actor_type: str
    actor_role_snapshot: str | None
    actor_name_snapshot: str | None


def normalize_ip(value: str) -> str:
    return ipaddress.ip_address(value).compressed


def pseudonymize_ip(value: str, secret: str) -> str:
    normalized = normalize_ip(value)
    return hmac.new(
        secret.encode("utf-8"),
        normalized.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def network_prefix_for_ip(value: str) -> str:
    ip = ipaddress.ip_address(normalize_ip(value))
    if ip.version == 4:
        return str(ipaddress.ip_network(f"{ip}/24", strict=False))
    return str(ipaddress.ip_network(f"{ip}/64", strict=False))


def encrypt_ip(value: str, encryption_key: str) -> str:
    token = Fernet(encryption_key.encode("utf-8")).encrypt(
        normalize_ip(value).encode("utf-8")
    )
    return token.decode("utf-8")


def summarize_user_agent(user_agent: str | None) -> str | None:
    if not user_agent:
        return None
    compact = " ".join(user_agent.split())
    return compact[:150] if compact else None


def actor_from_user(user: User | None, *, actor_type: str = "user") -> AuditActor:
    if user is None:
        return AuditActor(
            actor_id=None,
            actor_type=actor_type,
            actor_role_snapshot=None,
            actor_name_snapshot=None,
        )
    name_parts = [user.name.strip(), user.last_name.strip()]
    actor_name = " ".join(part for part in name_parts if part)
    return AuditActor(
        actor_id=user.id,
        actor_type=actor_type,
        actor_role_snapshot=normalize_user_role(user.role),
        actor_name_snapshot=actor_name or None,
    )


def extract_client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",", 1)[0].strip()
        if first:
            return first
    if request.client and request.client.host:
        return request.client.host
    return None


def current_trace_id() -> str | None:
    try:
        from opentelemetry import trace
        from opentelemetry.trace import format_trace_id

        span = trace.get_current_span()
        context = span.get_span_context()
        if context.is_valid:
            return format_trace_id(context.trace_id)
    except Exception:
        return None
    return None


def request_id_from_request(request: Request) -> str | None:
    for header in ("x-request-id", "x-cloud-trace-context"):
        value = request.headers.get(header)
        if value:
            return value[:128]
    return None


def session_id_from_request(request: Request) -> str | None:
    return getattr(request.state, "auth_session_id", None)


def should_store_encrypted_ip(action: str) -> bool:
    return action in HIGH_VALUE_IP_ACTIONS


def user_has_admin_access(user: User) -> bool:
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True
    return is_admin_role(getattr(user, "role", None))


def user_capabilities(user: User) -> dict[str, bool]:
    can_access_admin_panel = user_has_admin_access(user)
    clinical_access_enabled = bool(getattr(user, "clinical_access_enabled", False))
    return {
        "can_access_admin_panel": can_access_admin_panel,
        "can_view_audit": can_access_admin_panel,
        "can_manage_users": can_access_admin_panel,
        "can_use_clinical_features": clinical_access_enabled,
    }


async def create_audit_user_session(
    session: AsyncSession,
    *,
    user: User,
    request: Request,
    settings: Settings,
    organization_id: str | None = None,
    session_id: str | None = None,
) -> AuditUserSession:
    ip_value = extract_client_ip(request) or "127.0.0.1"
    now = datetime.now(timezone.utc)
    audit_session = AuditUserSession(
        id=session_id or str(uuid4()),
        organization_id=organization_id,
        user_id=user.id,
        ip_hmac=pseudonymize_ip(ip_value, settings.audit_ip_hmac_secret),
        network_prefix=network_prefix_for_ip(ip_value),
        ip_encrypted=encrypt_ip(ip_value, settings.audit_ip_encryption_key),
        user_agent_summary=summarize_user_agent(request.headers.get("user-agent")),
        started_at=now,
        last_seen_at=now,
        ended_at=None,
    )
    session.add(audit_session)
    await session.flush()
    return audit_session


async def touch_audit_user_session(
    session: AsyncSession,
    *,
    session_id: str | None,
) -> None:
    if not session_id:
        return
    audit_session = await session.get(AuditUserSession, session_id)
    if audit_session is None:
        return
    audit_session.last_seen_at = datetime.now(timezone.utc)
    await session.flush()


async def end_audit_user_session(
    session: AsyncSession,
    *,
    session_id: str | None,
) -> None:
    if not session_id:
        return
    audit_session = await session.get(AuditUserSession, session_id)
    if audit_session is None:
        return
    now = datetime.now(timezone.utc)
    audit_session.last_seen_at = now
    audit_session.ended_at = now
    await session.flush()


async def record_audit_event(
    session: AsyncSession,
    *,
    action: str,
    result: str,
    request: Request | None = None,
    actor: AuditActor | None = None,
    session_id: str | None = None,
    organization_id: str | None = None,
    patient_id: int | None = None,
    encounter_id: int | None = None,
    document_id: int | None = None,
    resource_type: str | None = None,
    resource_id: str | int | None = None,
    service_name: str | None = None,
    service_account: str | None = None,
    error_code: str | None = None,
) -> AuditEvent:
    if actor is None:
        actor = AuditActor(None, "system", None, None)

    event = AuditEvent(
        organization_id=organization_id,
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
        actor_role_snapshot=actor.actor_role_snapshot,
        actor_name_snapshot=actor.actor_name_snapshot,
        action=action,
        result=result,
        session_id=session_id,
        patient_id=patient_id,
        encounter_id=encounter_id,
        document_id=document_id,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        service_name=service_name,
        service_account=service_account,
        error_code=error_code,
        trace_id=current_trace_id(),
        request_id=request_id_from_request(request) if request else None,
        created_at=datetime.now(timezone.utc),
    )
    session.add(event)
    await session.flush()
    return event


async def record_security_event(
    session: AsyncSession,
    *,
    action: str,
    result: str,
    request: Request,
    settings: Settings,
    actor: AuditActor | None = None,
    session_id: str | None = None,
    error_code: str | None = None,
    resource_type: str | None = None,
    resource_id: str | int | None = None,
) -> AuditEvent:
    ip_value = extract_client_ip(request)
    if session_id and ip_value:
        audit_session = await session.get(AuditUserSession, session_id)
        if audit_session is not None and should_store_encrypted_ip(action):
            audit_session.ip_encrypted = encrypt_ip(
                ip_value,
                settings.audit_ip_encryption_key,
            )
            audit_session.ip_hmac = pseudonymize_ip(ip_value, settings.audit_ip_hmac_secret)
            audit_session.network_prefix = network_prefix_for_ip(ip_value)
            audit_session.last_seen_at = datetime.now(timezone.utc)
    return await record_audit_event(
        session,
        action=action,
        result=result,
        request=request,
        actor=actor,
        session_id=session_id,
        error_code=error_code,
        resource_type=resource_type,
        resource_id=resource_id,
    )


def require_audit_reader(user: User) -> None:
    if user_has_admin_access(user):
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Audit access denied")


def require_user_manager(user: User) -> None:
    if user_capabilities(user)["can_manage_users"]:
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "User management denied")


async def query_audit_events(
    session: AsyncSession,
    *,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    action: str | None = None,
    actor_id: int | None = None,
    patient_id: int | None = None,
    encounter_id: int | None = None,
    document_id: int | None = None,
    session_id: str | None = None,
    result: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AuditEvent], int]:
    stmt: Select[tuple[AuditEvent]] = select(AuditEvent)
    if start_at is not None:
        stmt = stmt.where(AuditEvent.created_at >= start_at)
    if end_at is not None:
        stmt = stmt.where(AuditEvent.created_at <= end_at)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if actor_id is not None:
        stmt = stmt.where(AuditEvent.actor_id == actor_id)
    if patient_id is not None:
        stmt = stmt.where(AuditEvent.patient_id == patient_id)
    if encounter_id is not None:
        stmt = stmt.where(AuditEvent.encounter_id == encounter_id)
    if document_id is not None:
        stmt = stmt.where(AuditEvent.document_id == document_id)
    if session_id:
        stmt = stmt.where(AuditEvent.session_id == session_id)
    if result:
        stmt = stmt.where(AuditEvent.result == result)
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = int((await session.execute(count_stmt)).scalar_one() or 0)
    stmt = stmt.order_by(AuditEvent.created_at.desc()).limit(limit).offset(offset)
    result_obj = await session.execute(stmt)
    return list(result_obj.scalars().all()), total
