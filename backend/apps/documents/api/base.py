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
from apps.documents.services.rich_document_content import (
    build_synced_document_content,
    set_document_content_fields,
)

import logging

logger = logging.getLogger(__name__)
router = Router()


def _resolve_payload_markdown(payload: DocumentCreateIn | DocumentContentUpdateIn) -> str:
    if payload.content_markdown is not None:
        return payload.content_markdown
    if payload.content is not None:
        return payload.content
    return ""


def _resolve_payload_json(
    payload: DocumentCreateIn | DocumentContentUpdateIn,
):
    return payload.content_json


def _editor_payload_source(
    payload: DocumentCreateIn | DocumentContentUpdateIn,
) -> str:
    if payload.content_json is not None:
        return "json"
    return "markdown"


def _serialize_document(doc: Document, doctor_id: int | None = None) -> dict:
    return {
        "id": doc.id,
        "encounter_id": doc.encounter_id,
        "kind": doc.kind,
        "doctor_template_id": doc.doctor_template_id,
        "doctor_template_name": doc.doctor_template.name if doc.doctor_template else None,
        "content": doc.content_markdown,
        "content_markdown": doc.content_markdown,
        "content_json": doc.content_json,
        "doctor_id": doctor_id if doctor_id is not None else doc.doctor_id,
        "created_on": doc.created_on,
    }


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

        synced_content = build_synced_document_content(
            content_markdown=_resolve_payload_markdown(payload),
            content_json=_resolve_payload_json(payload),
            preferred_source=_editor_payload_source(payload),
        )

        doc = Document.objects.create(
            encounter_id=payload.encounter_id,
            kind=payload.kind,
            doctor_template_id=doctor_template_id,
            content_markdown=synced_content.content_markdown,
            content_json=synced_content.content_json,
            doctor=doctor,
        )

        return _serialize_document(doc, doctor.id)
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

        docs = Document.objects.filter(encounter=enc).select_related("doctor_template")

        result = []
        for doc in docs:
            result.append(_serialize_document(doc))

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

        set_document_content_fields(
            doc,
            content_markdown=_resolve_payload_markdown(payload),
            content_json=_resolve_payload_json(payload),
            preferred_source=_editor_payload_source(payload),
        )
        doc.save(update_fields=["content_markdown", "content_json"])
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

        return {
            "content": doc.content_markdown,
            "content_markdown": doc.content_markdown,
            "content_json": doc.content_json,
        }
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
