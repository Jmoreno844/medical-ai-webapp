"""
Cloud Function callbacks (JWT Bearer) — chunks, transcription PATCH, notify.
"""

import logging

from django.http import Http404
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from ninja import Router
from ninja.errors import HttpError
from apps.documentos.models import Documento
from apps.documentos.schemas import (
    DocumentoUpdateIn,
    GenerationChunkIn,
    SuccessResponse,
    TranscriptionNotificationIn,
)
from apps.documentos.services.sse_hub import (
    notify_document_updated,
    notify_generation_progress,
)
from utils.auth import JWTAuth
from utils.jwt_http import resolve_bearer_jwt_payload

logger = logging.getLogger(__name__)
router = Router()


@router.post("/document/generation-chunk", auth=JWTAuth())
@csrf_exempt
def receive_generation_chunk(request, payload: GenerationChunkIn, auth=None):
    """
    Receive a chunk of generated content from the cloud function.
    Broadcast to connected clients and update document.
    """
    auth = resolve_bearer_jwt_payload(request, auth)
    if not auth:
        logger.warning("generation-chunk: missing or invalid JWT")
        raise HttpError(401, "Authentication required")

    id_documento = payload.id_documento
    id_proceso = payload.id_proceso

    try:
        id_documento_from_token = auth.get("id_documento")
        id_proceso_from_token = auth.get("id_proceso")

        if int(id_documento_from_token) != id_documento:
            logger.warning(
                "Document ID mismatch: %s != %s", id_documento_from_token, id_documento
            )
            raise HttpError(403, "Invalid document ID")

        if id_proceso_from_token != id_proceso:
            logger.warning(
                "Processing ID mismatch: %s != %s",
                id_proceso_from_token,
                id_proceso,
            )
            raise HttpError(403, "Invalid processing ID")

        documento = get_object_or_404(Documento, id=id_documento)

        if payload.is_complete:
            if payload.chunk:
                documento.contenido = payload.chunk
            documento.save()
            notify_generation_progress(
                id_documento, id_proceso, chunk=payload.chunk, is_complete=True
            )
            return {
                "success": True,
                "message": f"Generación completada para documento {id_documento}",
            }

        if payload.is_error:
            notify_generation_progress(
                id_documento,
                id_proceso,
                error=payload.error or "Error en la generación",
            )
            return {
                "success": False,
                "error": payload.error or "Error en la generación",
            }

        notify_generation_progress(id_documento, id_proceso, chunk=payload.chunk)
        return {
            "success": True,
            "message": f"Chunk received for document {id_documento}",
        }

    except Http404:
        logger.error("Documento %s not found", id_documento)
        raise HttpError(404, "Documento no encontrado")


@router.patch(
    "/documento_by_function/{documento_id}",
    response=SuccessResponse,
    auth=JWTAuth(),
)
@csrf_exempt
def update_documento_content(
    request, documento_id: int, payload: DocumentoUpdateIn, auth=None
):
    """Update document content from transcription Cloud Function."""
    auth = resolve_bearer_jwt_payload(request, auth)
    if not auth:
        raise HttpError(401, "Authentication required")

    id_documento_from_token = auth.get("id_documento")
    id_medico_from_token = auth.get("id_usuario")

    try:
        documento = get_object_or_404(Documento, id=documento_id)

        if documento.id_medico.id != id_medico_from_token:
            raise HttpError(403, "No tienes permiso para modificar este documento")

        if int(id_documento_from_token) != int(documento_id):
            raise HttpError(403, "No tienes permiso para modificar este documento")

        documento.contenido = payload.contenido
        documento.save()
        notify_document_updated(documento_id, "transcription_complete")
        return {
            "success": True,
            "message": f"Documento {documento_id} actualizado exitosamente",
        }
    except Http404:
        logger.error("Documento %s not found", documento_id)
        raise HttpError(404, "Documento no encontrado")


@router.post("/notify/transcription-complete", auth=JWTAuth())
def transcription_complete_notification(
    request, payload: TranscriptionNotificationIn, auth=None
):
    """Cloud Function notifies transcription pipeline completion."""
    auth = resolve_bearer_jwt_payload(request, auth)
    if not auth:
        raise HttpError(401, "Authentication required")

    id_documento = payload.id_documento

    try:
        documento = get_object_or_404(Documento, id=id_documento)
        document_id_from_token = auth.get("id_documento")
        doctor_id_from_token = auth.get("id_usuario")

        if int(document_id_from_token) != id_documento:
            raise HttpError(403, "Invalid document ID in token")

        if documento.id_medico.id != doctor_id_from_token:
            raise HttpError(403, "No tienes permiso para este documento")

        notify_document_updated(id_documento, "transcription_complete")
        return {
            "success": True,
            "message": f"Notificación enviada para documento {id_documento}",
        }
    except Http404:
        logger.error("Documento %s not found", id_documento)
        raise HttpError(404, "Documento no encontrado")
