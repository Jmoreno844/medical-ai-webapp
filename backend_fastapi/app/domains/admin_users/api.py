from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schemas import SuccessResponse
from app.db.models import User
from app.db.session import get_db_session
from app.domains.admin_users.schemas import (
    AdminUserDetailOut,
    AdminUserListOut,
    AdminUserSessionOut,
    AdminUserStatusUpdate,
)
from app.domains.admin_users.service import (
    get_admin_user_summary,
    get_recent_user_events,
    get_recent_user_sessions,
    list_admin_users,
)
from app.domains.audit.schemas import AuditEventOut
from app.domains.audit.service import (
    actor_from_user,
    record_audit_event,
    require_user_manager,
    session_id_from_request,
)
from app.domains.auth.service import get_current_user

router = APIRouter()


@router.get("/internal/users", response_model=AdminUserListOut)
async def get_internal_users(
    q: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    role: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> AdminUserListOut:
    require_user_manager(user)
    items, total = await list_admin_users(
        session,
        q=q,
        is_active=is_active,
        role=role,
        limit=limit,
        offset=offset,
    )
    return AdminUserListOut(items=items, total=total, limit=limit, offset=offset)


@router.get("/internal/users/{user_id}", response_model=AdminUserDetailOut)
async def get_internal_user_detail(
    user_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> AdminUserDetailOut:
    require_user_manager(user)
    user_summary = await get_admin_user_summary(session, user_id=user_id)
    if user_summary is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    sessions = await get_recent_user_sessions(session, user_id=user_id)
    events = await get_recent_user_events(session, user_id=user_id)
    return AdminUserDetailOut(
        user=user_summary,
        sessions=[AdminUserSessionOut.model_validate(item) for item in sessions],
        recent_events=[AuditEventOut.model_validate(item) for item in events],
    )


@router.patch("/internal/users/{user_id}/status", response_model=SuccessResponse)
async def update_internal_user_status(
    user_id: int,
    payload: AdminUserStatusUpdate,
    request: Request,
    acting_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> SuccessResponse:
    require_user_manager(acting_user)
    target_user = await session.get(User, user_id)
    if target_user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if target_user.id == acting_user.id and payload.is_active is False:
        raise HTTPException(
            status_code=400,
            detail="No puedes desactivar tu propia cuenta",
        )

    target_user.is_active = payload.is_active
    await record_audit_event(
        session,
        action="user.activated" if payload.is_active else "user.deactivated",
        result="success",
        request=request,
        actor=actor_from_user(acting_user),
        session_id=session_id_from_request(request),
        resource_type="user",
        resource_id=target_user.id,
    )
    await session.commit()
    return SuccessResponse(success=True)
