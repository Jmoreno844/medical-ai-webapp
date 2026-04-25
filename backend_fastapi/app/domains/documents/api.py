from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.session import get_db_session
from app.domains.auth.service import get_current_user
from app.domains.documents.service import (
    create_document,
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
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentOut:
    try:
        document = await create_document(session, payload=payload, doctor_id=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    return serialize_document(document)


@router.get("/documents/encounter/{encounter_id}", response_model=list[DocumentOut])
async def get_documents_by_encounter(
    encounter_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[DocumentOut]:
    documents = await list_documents_for_encounter(
        session,
        encounter_id=encounter_id,
        doctor_id=user.id,
    )
    return [serialize_document(document) for document in documents]


@router.patch("/documents/by-editor/{document_id}", response_model=SuccessResponse)
async def update_document_by_editor(
    document_id: int,
    payload: DocumentContentUpdate,
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento no encontrado")
    await session.commit()
    return SuccessResponse(
        success=True,
        message=f"Documento {document_id} actualizado exitosamente",
    )


@router.get("/documents/{document_id}", response_model=DocumentContentOut)
async def get_document_content(
    document_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentContentOut:
    document = await get_document_for_doctor(
        session,
        document_id=document_id,
        doctor_id=user.id,
    )
    if not document:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento no encontrado")
    return DocumentContentOut(
        content=document.content_markdown,
        content_markdown=document.content_markdown,
        content_json=document.content_json,
    )


@router.delete("/documents/{document_id}", response_model=SuccessResponse)
async def delete_document(
    document_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> SuccessResponse:
    document = await get_document_for_doctor(
        session,
        document_id=document_id,
        doctor_id=user.id,
    )
    if not document:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento no encontrado")
    await session.delete(document)
    await session.commit()
    return SuccessResponse(
        success=True,
        message=f"Documento {document_id} eliminado exitosamente",
    )

