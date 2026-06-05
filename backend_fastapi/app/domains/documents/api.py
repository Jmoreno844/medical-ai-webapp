from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.audit.service import actor_from_user, record_audit_event, record_security_event
from app.db.models import User
from app.db.session import get_db_session
from app.domains.auth.service import get_current_user
from app.domains.documents.service import (
    create_document,
    delete_document_for_doctor,
    get_document_for_doctor,
    list_documents_for_encounter,
    serialize_document,
    update_document_content,
)
from app.core.schemas import SuccessResponse
from app.domains.documents.schemas import (
    DocumentContentOut,
    DocumentContentUpdate,
    DocumentCreate,
    DocumentOut,
)

router = APIRouter()


@router.post("/documents", response_model=DocumentOut)
async def create_document_endpoint(
    payload: DocumentCreate,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentOut:
    try:
        document = await create_document(session, payload=payload, doctor_id=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await record_audit_event(
        session,
        action="document.created",
        result="success",
        request=request,
        actor=actor_from_user(user),
        session_id=getattr(request.state, "auth_session_id", None),
        encounter_id=document.encounter_id,
        document_id=document.id,
        resource_type="document",
        resource_id=document.id,
    )
    await session.commit()
    return serialize_document(document)


@router.get("/documents/encounter/{encounter_id}", response_model=list[DocumentOut])
async def get_documents_by_encounter(
    encounter_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[DocumentOut]:
    documents = await list_documents_for_encounter(
        session,
        encounter_id=encounter_id,
        doctor_id=user.id,
    )
    await record_audit_event(
        session,
        action="clinical.encounter_opened",
        result="success",
        request=request,
        actor=actor_from_user(user),
        session_id=getattr(request.state, "auth_session_id", None),
        encounter_id=encounter_id,
        resource_type="encounter",
        resource_id=encounter_id,
    )
    await session.commit()
    return [serialize_document(document) for document in documents]


@router.patch("/documents/by-editor/{document_id}", response_model=SuccessResponse)
async def update_document_by_editor(
    document_id: int,
    payload: DocumentContentUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> SuccessResponse:
    document = await update_document_content(
        session,
        document_id=document_id,
        doctor_id=user.id,
        payload=payload,
    )
    if not document:
        await record_security_event(
            session,
            action="clinical.access_denied",
            result="denied",
            request=request,
            settings=request.app.state.settings,
            actor=actor_from_user(user),
            session_id=getattr(request.state, "auth_session_id", None),
            resource_type="document",
            resource_id=document_id,
        )
        await session.commit()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento no encontrado")
    await record_audit_event(
        session,
        action="document.edited",
        result="success",
        request=request,
        actor=actor_from_user(user),
        session_id=getattr(request.state, "auth_session_id", None),
        encounter_id=document.encounter_id,
        document_id=document.id,
        resource_type="document",
        resource_id=document.id,
    )
    await session.commit()
    return SuccessResponse(
        success=True,
        message=f"Documento {document_id} actualizado exitosamente",
    )


@router.get("/documents/{document_id}", response_model=DocumentContentOut)
async def get_document_content(
    document_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentContentOut:
    document = await get_document_for_doctor(
        session,
        document_id=document_id,
        doctor_id=user.id,
    )
    if not document:
        await record_security_event(
            session,
            action="clinical.access_denied",
            result="denied",
            request=request,
            settings=request.app.state.settings,
            actor=actor_from_user(user),
            session_id=getattr(request.state, "auth_session_id", None),
            resource_type="document",
            resource_id=document_id,
        )
        await session.commit()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento no encontrado")
    await record_audit_event(
        session,
        action="clinical.document_opened",
        result="success",
        request=request,
        actor=actor_from_user(user),
        session_id=getattr(request.state, "auth_session_id", None),
        encounter_id=document.encounter_id,
        document_id=document.id,
        resource_type="document",
        resource_id=document.id,
    )
    await session.commit()
    return DocumentContentOut(
        content=document.content_markdown,
        content_markdown=document.content_markdown,
        content_json=document.content_json,
    )


@router.delete("/documents/{document_id}", response_model=SuccessResponse)
async def delete_document(
    document_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> SuccessResponse:
    document = await get_document_for_doctor(
        session,
        document_id=document_id,
        doctor_id=user.id,
    )
    if not document:
        await record_security_event(
            session,
            action="clinical.access_denied",
            result="denied",
            request=request,
            settings=request.app.state.settings,
            actor=actor_from_user(user),
            session_id=getattr(request.state, "auth_session_id", None),
            resource_type="document",
            resource_id=document_id,
        )
        await session.commit()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento no encontrado")
    deleted = await delete_document_for_doctor(
        session,
        document_id=document_id,
        doctor_id=user.id,
    )
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento no encontrado")
    await record_audit_event(
        session,
        action="document.deleted",
        result="success",
        request=request,
        actor=actor_from_user(user),
        session_id=getattr(request.state, "auth_session_id", None),
        encounter_id=document.encounter_id,
        document_id=document.id,
        resource_type="document",
        resource_id=document.id,
    )
    await session.commit()
    return SuccessResponse(
        success=True,
        message=f"Documento {document_id} eliminado exitosamente",
    )
