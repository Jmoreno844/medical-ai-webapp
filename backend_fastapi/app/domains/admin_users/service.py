from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditEvent, AuditUserSession, User
from app.domains.admin_users.schemas import AdminUserListItem
from app.domains.auth.roles import normalize_user_role


def _user_metrics_columns(now: datetime) -> tuple:
    login_window_start = now - timedelta(hours=24)
    active_session_count = (
        select(func.count(AuditUserSession.id))
        .where(
            AuditUserSession.user_id == User.id,
            AuditUserSession.ended_at.is_(None),
        )
        .correlate(User)
        .scalar_subquery()
    )
    last_session_started_at = (
        select(func.max(AuditUserSession.started_at))
        .where(AuditUserSession.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )
    login_success_24h = (
        select(func.count(AuditEvent.id))
        .where(
            AuditEvent.actor_id == User.id,
            AuditEvent.action == "auth.login_success",
            AuditEvent.created_at >= login_window_start,
        )
        .correlate(User)
        .scalar_subquery()
    )
    login_failure_24h = (
        select(func.count(AuditEvent.id))
        .where(
            AuditEvent.actor_id == User.id,
            AuditEvent.action == "auth.login_failure",
            AuditEvent.created_at >= login_window_start,
        )
        .correlate(User)
        .scalar_subquery()
    )
    return (
        active_session_count,
        last_session_started_at,
        login_success_24h,
        login_failure_24h,
    )


async def list_admin_users(
    session: AsyncSession,
    *,
    q: str | None = None,
    is_active: bool | None = None,
    clinical_access_enabled: bool | None = None,
    role: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AdminUserListItem], int]:
    now = datetime.now(timezone.utc)
    (
        active_session_count,
        last_session_started_at,
        login_success_24h,
        login_failure_24h,
    ) = _user_metrics_columns(now)
    stmt = select(
        User.id,
        User.email,
        User.name,
        User.last_name,
        User.role,
        User.is_active,
        User.clinical_access_enabled,
        User.last_login,
        User.date_joined,
        active_session_count.label("active_session_count"),
        last_session_started_at.label("last_session_started_at"),
        login_success_24h.label("login_success_24h"),
        login_failure_24h.label("login_failure_24h"),
    )
    if q:
        search = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                User.email.ilike(search),
                User.name.ilike(search),
                User.last_name.ilike(search),
            )
        )
    if is_active is not None:
        stmt = stmt.where(User.is_active.is_(is_active))
    if clinical_access_enabled is not None:
        stmt = stmt.where(User.clinical_access_enabled.is_(clinical_access_enabled))
    if role:
        stmt = stmt.where(User.role == normalize_user_role(role))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = int((await session.execute(count_stmt)).scalar_one() or 0)

    stmt = stmt.order_by(User.date_joined.desc()).limit(limit).offset(offset)
    rows = (await session.execute(stmt)).mappings().all()
    return [AdminUserListItem.model_validate(row) for row in rows], total


async def get_admin_user_summary(
    session: AsyncSession,
    *,
    user_id: int,
) -> AdminUserListItem | None:
    now = datetime.now(timezone.utc)
    (
        active_session_count,
        last_session_started_at,
        login_success_24h,
        login_failure_24h,
    ) = _user_metrics_columns(now)
    stmt = select(
        User.id,
        User.email,
        User.name,
        User.last_name,
        User.role,
        User.is_active,
        User.clinical_access_enabled,
        User.last_login,
        User.date_joined,
        active_session_count.label("active_session_count"),
        last_session_started_at.label("last_session_started_at"),
        login_success_24h.label("login_success_24h"),
        login_failure_24h.label("login_failure_24h"),
    ).where(User.id == user_id)
    row = (await session.execute(stmt)).mappings().one_or_none()
    if row is None:
        return None
    return AdminUserListItem.model_validate(row)


async def get_recent_user_sessions(
    session: AsyncSession,
    *,
    user_id: int,
    limit: int = 10,
) -> list[AuditUserSession]:
    result = await session.execute(
        select(AuditUserSession)
        .where(AuditUserSession.user_id == user_id)
        .order_by(AuditUserSession.started_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_recent_user_events(
    session: AsyncSession,
    *,
    user_id: int,
    limit: int = 25,
) -> list[AuditEvent]:
    result = await session.execute(
        select(AuditEvent)
        .where(AuditEvent.actor_id == user_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
