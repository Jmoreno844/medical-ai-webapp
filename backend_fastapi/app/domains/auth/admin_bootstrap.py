from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.domains.audit.service import AuditActor, record_audit_event
from app.domains.auth.roles import ADMIN_ROLE
from app.domains.auth.service import register_doctor_user
from app.core.security import make_django_password


@dataclass(slots=True)
class AdminBootstrapResult:
    user: User
    created: bool
    promoted: bool
    reactivated: bool
    password_updated: bool


def _script_actor() -> AuditActor:
    return AuditActor(
        actor_id=None,
        actor_type="system",
        actor_role_snapshot=ADMIN_ROLE,
        actor_name_snapshot="create_admin_script",
    )


async def create_or_promote_admin_user(
    session: AsyncSession,
    *,
    email: str,
    password: str | None,
    name: str,
    last_name: str,
    make_superuser: bool = False,
    update_password: bool = False,
) -> AdminBootstrapResult:
    normalized_email = email.strip().lower()
    existing = await session.scalar(select(User).where(User.email == normalized_email))
    created = False
    promoted = False
    reactivated = False
    password_updated = False

    if existing is None:
        if not password:
            raise ValueError("Password is required when creating a new admin user")
        user = await register_doctor_user(
            session,
            email=normalized_email,
            password=password,
            name=name,
            last_name=last_name,
        )
        user.clinical_access_enabled = True
        created = True
        await record_audit_event(
            session,
            action="user.created",
            result="success",
            actor=_script_actor(),
            resource_type="user",
            resource_id=user.id,
        )
    else:
        user = existing
        user.name = name.strip()
        user.last_name = last_name.strip()
        user.clinical_access_enabled = True
        if not user.is_active:
            user.is_active = True
            reactivated = True
        if password and update_password:
            user.password = make_django_password(password)
            password_updated = True

    if user.role != ADMIN_ROLE or not user.is_staff or (make_superuser and not user.is_superuser):
        user.role = ADMIN_ROLE
        user.is_staff = True
        user.clinical_access_enabled = True
        if make_superuser:
            user.is_superuser = True
        promoted = True
        await record_audit_event(
            session,
            action="user.role_changed",
            result="success",
            actor=_script_actor(),
            resource_type="user",
            resource_id=user.id,
        )

    if reactivated:
        await record_audit_event(
            session,
            action="user.activated",
            result="success",
            actor=_script_actor(),
            resource_type="user",
            resource_id=user.id,
        )

    await session.flush()
    return AdminBootstrapResult(
        user=user,
        created=created,
        promoted=promoted,
        reactivated=reactivated,
        password_updated=password_updated,
    )
