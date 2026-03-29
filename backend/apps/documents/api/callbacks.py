"""
Cloud Function callbacks (JWT Bearer) — chunks, transcription PATCH, notify.
"""

import logging

from django.http import Http404
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from ninja import Router
from ninja.errors import HttpError
from apps.documents.models import Document
from apps.documents.schemas import (
    DocumentContentUpdateIn,
    GenerationChunkIn,
    SuccessResponse,
    TranscriptionNotificationIn,
)
from apps.documents.services.sse_hub import (
    notify_document_updated,
    notify_generation_progress,
)
from utils.auth import JWTAuth
from utils.jwt_http import resolve_bearer_jwt_payload

logger = logging.getLogger(__name__)
router = Router()


@router.post("/documents/generation-chunk", auth=JWTAuth())
@csrf_exempt
def receive_generation_chunk(request, payload: GenerationChunkIn, auth=None):
    auth = resolve_bearer_jwt_payload(request, auth)
    if not auth:
        logger.warning("generation-chunk: missing or invalid JWT")
        raise HttpError(401, "Authentication required")

    document_id = payload.document_id
    process_id = payload.process_id

    try:
        doc_id_from_token = auth.get("document_id")
        process_id_from_token = auth.get("process_id")

        if int(doc_id_from_token) != document_id:
            logger.warning(
                "Document ID mismatch: %s != %s", doc_id_from_token, document_id
            )
            raise HttpError(403, "Invalid document ID")

        if process_id_from_token != process_id:
            logger.warning(
                "Processing ID mismatch: %s != %s",
                process_id_from_token,
                process_id,
            )
            raise HttpError(403, "Invalid processing ID")

        doc = get_object_or_404(Document, id=document_id)

        if payload.is_complete:
            if payload.chunk:
                doc.content = payload.chunk
            doc.save()
            notify_generation_progress(
                document_id, process_id, chunk=payload.chunk, is_complete=True
            )
            return {
                "success": True,
                "message": f"Generación completada para documento {document_id}",
            }

        if payload.is_error:
            notify_generation_progress(
                document_id,
                process_id,
                error=payload.error or "Error en la generación",
            )
            return {
                "success": False,
                "error": payload.error or "Error en la generación",
            }

        notify_generation_progress(document_id, process_id, chunk=payload.chunk)
        return {
            "success": True,
            "message": f"Chunk received for document {document_id}",
        }

    except Http404:
        logger.error("Document %s not found", document_id)
        raise HttpError(404, "Documento no encontrado")


@router.patch(
    "/documents/by-function/{document_id}",
    response=SuccessResponse,
    auth=JWTAuth(),
)
@csrf_exempt
def update_document_by_function(
    request, document_id: int, payload: DocumentContentUpdateIn, auth=None
):
    auth = resolve_bearer_jwt_payload(request, auth)
    if not auth:
        raise HttpError(401, "Authentication required")

    doc_id_from_token = auth.get("document_id")
    doctor_id_from_token = auth.get("user_id")

    try:
        doc = get_object_or_404(Document, id=document_id)

        if doc.doctor.id != doctor_id_from_token:
            raise HttpError(403, "No tienes permiso para modificar este documento")

        if int(doc_id_from_token) != int(document_id):
            raise HttpError(403, "No tienes permiso para modificar este documento")

        doc.content = payload.content
        doc.save()
        notify_document_updated(document_id, "transcription_complete")
        return {
            "success": True,
            "message": f"Documento {document_id} actualizado exitosamente",
        }
    except Http404:
        logger.error("Document %s not found", document_id)
        raise HttpError(404, "Documento no encontrado")


@router.post("/transcription/notify-complete", auth=JWTAuth())
def transcription_complete_notification(
    request, payload: TranscriptionNotificationIn, auth=None
):
    auth = resolve_bearer_jwt_payload(request, auth)
    if not auth:
        raise HttpError(401, "Authentication required")

    document_id = payload.document_id

    try:
        doc = get_object_or_404(Document, id=document_id)
        document_id_from_token = auth.get("document_id")
        doctor_id_from_token = auth.get("user_id")

        if int(document_id_from_token) != document_id:
            raise HttpError(403, "Invalid document ID in token")

        if doc.doctor.id != doctor_id_from_token:
            raise HttpError(403, "No tienes permiso para este documento")

        notify_document_updated(document_id, "transcription_complete")
        return {
            "success": True,
            "message": f"Notificación enviada para documento {document_id}",
        }
    except Http404:
        logger.error("Document %s not found", document_id)
        raise HttpError(404, "Documento no encontrado")
