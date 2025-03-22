from typing import List
from ninja import Router
from ninja.errors import HttpError
from django.shortcuts import get_object_or_404
from django.http import Http404
from ninja.security import django_auth

from apps.documentos.models import Documento
from apps.documentos.schemas import (
    DocumentoIn,
    DocumentoOut,
    DocumentoUpdateIn,
    SuccessResponse,
    DocumentoContentOut,
)
from apps.encuentro.models import Encuentro

import logging

logger = logging.getLogger(__name__)
router = Router()


@router.post("/documento", response=DocumentoOut, auth=django_auth)
def create_documento(request, payload: DocumentoIn):
    """
    Create a new documento. If tipo is 'plantilla', id_plantilla_doctor is required.
    Contenido is optional and will be an empty string by default.
    """
    # Get the authenticated doctor
    doctor = request.user

    try:
        # Verify the encounter exists and belongs to this doctor
        try:
            encuentro = Encuentro.objects.get(id=payload.id_encuentro)
            if encuentro.id_medico.id != doctor.id:
                raise HttpError(403, "No tienes permiso para acceder a este encuentro")
        except Encuentro.DoesNotExist:
            raise HttpError(404, "Encuentro no encontrado")

        # Validate tipo is one of the allowed choices
        valid_tipos = [choice[0] for choice in Documento.TIPO_CHOICES]
        if payload.tipo not in valid_tipos:
            raise HttpError(
                400,
                f"Tipo de documento inválido. Opciones válidas: {', '.join(valid_tipos)}",
            )

        # Validate tipo and id_plantilla_doctor consistency
        if payload.tipo == "plantilla" and payload.id_plantilla_doctor is None:
            raise HttpError(
                400, "Se requiere id_plantilla_doctor cuando el tipo es 'plantilla'"
            )

        if payload.tipo != "plantilla" and payload.id_plantilla_doctor is not None:
            payload.id_plantilla_doctor = None  # Ensure consistency

        # Create the documento
        documento = Documento.objects.create(
            id_encuentro_id=payload.id_encuentro,
            tipo=payload.tipo,
            id_plantilla_doctor_id=payload.id_plantilla_doctor,
            contenido=payload.contenido if payload.contenido is not None else "",
            id_medico=doctor,
        )

        # Return the model converted to a dictionary with correct ID values
        return {
            "id": documento.id,
            "id_encuentro": documento.id_encuentro_id,
            "tipo": documento.tipo,
            "id_plantilla_doctor": documento.id_plantilla_doctor_id,
            "contenido": documento.contenido,
            "id_medico": doctor.id,
            "fecha_creacion": documento.fecha_creacion,
        }
    except Exception as e:
        logger.error(f"Error creating document: {str(e)}")
        raise HttpError(500, f"Error al crear documento: {str(e)}")


@router.get(
    "/documento/encuentro/{encuentro_id}", response=List[DocumentoOut], auth=django_auth
)
def get_documentos_by_encuentro(request, encuentro_id: int):
    """
    Get all documentos for a specific encounter.
    Validates that the encounter belongs to the requesting doctor.
    """
    doctor = request.user

    try:
        # First check if the encounter exists at all
        encuentro = get_object_or_404(Encuentro, id=encuentro_id)

        # Then check if the encounter belongs to this doctor
        if encuentro.id_medico.id != doctor.id:
            raise HttpError(403, "No tienes permiso para acceder a este encuentro")

        # Get all documents for this encounter
        documentos = Documento.objects.filter(id_encuentro=encuentro)

        # If no documents are found, return an empty list (not an error)

        # Convert to dictionary format
        result = []
        for doc in documentos:
            result.append(
                {
                    "id": doc.id,
                    "id_encuentro": doc.id_encuentro_id,
                    "tipo": doc.tipo,
                    "id_plantilla_doctor": doc.id_plantilla_doctor_id,
                    "contenido": doc.contenido,
                    "id_medico": doc.id_medico_id,
                    "fecha_creacion": doc.fecha_creacion,
                }
            )

        return result
    except Http404:
        raise HttpError(404, "Encuentro no encontrado")


@router.patch(
    "/documento_by_editor/{documento_id}", response=SuccessResponse, auth=django_auth
)
def update_documento_by_user(request, documento_id: int, payload: DocumentoUpdateIn):
    """
    Update the content of an existing document using Django authentication.
    Authentication is via the Django session.
    """
    doctor = request.user

    try:
        # Get the document and verify it exists
        documento = get_object_or_404(Documento, id=documento_id)

        # Verify the document belongs to the authenticated doctor
        if documento.id_medico.id != doctor.id:
            raise HttpError(403, "No tienes permiso para modificar este documento")

        # Update only the content field
        documento.contenido = payload.contenido
        documento.save()
        logger.info(
            f"Successfully updated documento {documento_id} by user {doctor.id}"
        )

        # Return simple success response
        return {
            "success": True,
            "message": f"Documento {documento_id} actualizado exitosamente",
        }
    except Http404:
        logger.error(f"Documento {documento_id} not found")
        raise HttpError(404, "Documento no encontrado")


@router.get("/debug-auth")
def debug_auth(request):
    headers = {key: value for key, value in request.headers.items()}
    return {"headers": headers}


@router.get("/documento/{documento_id}", response=DocumentoContentOut, auth=django_auth)
def get_documento_content(request, documento_id: int):
    """
    Get the content of a specific document.
    Validates that the document belongs to the requesting doctor.
    """
    doctor = request.user

    try:
        # Get the document and verify it exists
        documento = get_object_or_404(Documento, id=documento_id)

        # Verify the document belongs to the authenticated doctor
        if documento.id_medico.id != doctor.id:
            raise HttpError(403, "No tienes permiso para acceder a este documento")

        # Return just the content
        return {"contenido": documento.contenido}
    except Http404:
        raise HttpError(404, "Documento no encontrado")
