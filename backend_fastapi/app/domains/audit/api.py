from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schemas import SuccessResponse
from app.db.models import User
from app.db.session import get_db_session
from app.domains.audit.schemas import (
    CLIENT_AUDIT_ACTIONS,
    AuditClientEventIn,
    AuditEventListOut,
    AuditEventOut,
)
from app.domains.audit.service import (
    actor_from_user,
    query_audit_events,
    record_audit_event,
    require_audit_reader,
    session_id_from_request,
)
from app.domains.auth.service import get_current_user

router = APIRouter()


@router.post("/audit/client-events", response_model=SuccessResponse)
async def create_client_audit_event(
    payload: AuditClientEventIn,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> SuccessResponse:
    if payload.action not in CLIENT_AUDIT_ACTIONS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unsupported audit action")

    await record_audit_event(
        session,
        action=payload.action,
        result="success",
        request=request,
        actor=actor_from_user(user),
        session_id=session_id_from_request(request),
        patient_id=payload.patient_id,
        encounter_id=payload.encounter_id,
        document_id=payload.document_id,
        resource_type="client_event",
        resource_id=payload.document_id or payload.encounter_id or payload.patient_id,
    )
    await session.commit()
    return SuccessResponse(success=True)


@router.get("/internal/audit-events", response_model=AuditEventListOut)
async def list_audit_events(
    request: Request,
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    action: str | None = Query(default=None),
    actor_id: int | None = Query(default=None),
    patient_id: int | None = Query(default=None),
    encounter_id: int | None = Query(default=None),
    document_id: int | None = Query(default=None),
    session_id: str | None = Query(default=None),
    result: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> AuditEventListOut:
    require_audit_reader(user)
    items, total = await query_audit_events(
        session,
        start_at=start_at,
        end_at=end_at,
        action=action,
        actor_id=actor_id,
        patient_id=patient_id,
        encounter_id=encounter_id,
        document_id=document_id,
        session_id=session_id,
        result=result,
        limit=limit,
        offset=offset,
    )
    await record_audit_event(
        session,
        action="audit.audit_log_viewed",
        result="success",
        request=request,
        actor=actor_from_user(user),
        session_id=session_id_from_request(request),
        resource_type="audit_log",
        resource_id="internal_audit_events",
    )
    await session.commit()
    return AuditEventListOut(
        items=[AuditEventOut.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )
