from typing import List
from ninja import Router
from ninja.errors import HttpError
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.http import Http404
from ninja.security import django_auth

from apps.documents.models import Document
from apps.documents.schemas import (
    DocumentCreateIn,
    DocumentOut,
    DocumentContentUpdateIn,
    SuccessResponse,
    DocumentContentOut,
)
from apps.encounters.models import Encounter

import logging

logger = logging.getLogger(__name__)
router = Router()


@router.post("/documents", response=DocumentOut, auth=django_auth)
def create_document(request, payload: DocumentCreateIn):
    doctor = request.user

    try:
        try:
            enc = Encounter.objects.get(id=payload.encounter_id)
            if enc.doctor.id != doctor.id:
                raise HttpError(403, "No tienes permiso para acceder a este encuentro")
        except Encounter.DoesNotExist:
            raise HttpError(404, "Encuentro no encontrado")

        valid_kinds = [choice[0] for choice in Document.KIND_CHOICES]
        if payload.kind not in valid_kinds:
            raise HttpError(
                400,
                f"Tipo de documento inválido. Opciones válidas: {', '.join(valid_kinds)}",
            )

        if payload.kind == "template" and payload.doctor_template_id is None:
            raise HttpError(
                400, "Se requiere doctor_template_id cuando el kind es 'template'"
            )

        doctor_template_id = payload.doctor_template_id
        if payload.kind != "template":
            doctor_template_id = None

        doc = Document.objects.create(
            encounter_id=payload.encounter_id,
            kind=payload.kind,
            doctor_template_id=doctor_template_id,
            content=payload.content if payload.content is not None else "",
            doctor=doctor,
        )

        return {
            "id": doc.id,
            "encounter_id": doc.encounter_id,
            "kind": doc.kind,
            "doctor_template_id": doc.doctor_template_id,
            "content": doc.content,
            "doctor_id": doctor.id,
            "created_on": doc.created_on,
        }
    except Exception as e:
        logger.error(f"Error creating document: {str(e)}")
        raise HttpError(500, f"Error al crear documento: {str(e)}")


@router.get(
    "/documents/encounter/{encounter_id}", response=List[DocumentOut], auth=django_auth
)
def get_documents_by_encounter(request, encounter_id: int):
    doctor = request.user

    try:
        enc = get_object_or_404(Encounter, id=encounter_id)

        if enc.doctor.id != doctor.id:
            raise HttpError(403, "No tienes permiso para acceder a este encuentro")

        docs = Document.objects.filter(encounter=enc)

        result = []
        for doc in docs:
            result.append(
                {
                    "id": doc.id,
                    "encounter_id": doc.encounter_id,
                    "kind": doc.kind,
                    "doctor_template_id": doc.doctor_template_id,
                    "content": doc.content,
                    "doctor_id": doc.doctor_id,
                    "created_on": doc.created_on,
                }
            )

        return result
    except Http404:
        raise HttpError(404, "Encuentro no encontrado")


@router.patch(
    "/documents/by-editor/{document_id}", response=SuccessResponse, auth=django_auth
)
def update_document_by_editor(
    request, document_id: int, payload: DocumentContentUpdateIn
):
    doctor = request.user

    try:
        doc = get_object_or_404(Document, id=document_id)

        if doc.doctor.id != doctor.id:
            raise HttpError(403, "No tienes permiso para modificar este documento")

        doc.content = payload.content
        doc.save()
        logger.info(f"Successfully updated document {document_id} by user {doctor.id}")

        return {
            "success": True,
            "message": f"Documento {document_id} actualizado exitosamente",
        }
    except Http404:
        logger.error(f"Document {document_id} not found")
        raise HttpError(404, "Documento no encontrado")


@router.get("/debug-auth")
def debug_auth(request):
    """Only available when DEBUG=True (never expose headers in production)."""
    if not settings.DEBUG:
        raise HttpError(404, "Not found")
    headers = {key: value for key, value in request.headers.items()}
    return {"headers": headers}


@router.get("/documents/{document_id}", response=DocumentContentOut, auth=django_auth)
def get_document_content(request, document_id: int):
    doctor = request.user

    try:
        doc = get_object_or_404(Document, id=document_id)

        if doc.doctor.id != doctor.id:
            raise HttpError(403, "No tienes permiso para acceder a este documento")

        return {"content": doc.content}
    except Http404:
        raise HttpError(404, "Documento no encontrado")


@router.delete("/documents/{document_id}", response=SuccessResponse, auth=django_auth)
def delete_document(request, document_id: int):
    doctor = request.user

    try:
        doc = get_object_or_404(Document, id=document_id)

        if doc.doctor.id != doctor.id:
            raise HttpError(403, "No tienes permiso para acceder a este documento")

        doc.delete()
        logger.info(f"Successfully deleted document {document_id} by user {doctor.id}")

        return {
            "success": True,
            "message": f"Documento {document_id} eliminado exitosamente",
        }
    except Http404:
        logger.error(f"Document {document_id} not found")
        raise HttpError(404, "Documento no encontrado")
