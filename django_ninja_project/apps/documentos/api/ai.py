from ninja import Router
from ninja.errors import HttpError
from django.shortcuts import get_object_or_404
from django.http import Http404
from utils.auth import JWTAuth
import jwt
from django.conf import settings

from apps.documentos.models import Documento
from apps.documentos.schemas import (
    DocumentoUpdateIn,
    SuccessResponse,
    TranscriptionNotificationIn,
)

from .sse import notify_document_updated

import logging

logger = logging.getLogger(__name__)
router = Router()


@router.patch(
    "/documento_by_function/{documento_id}", response=SuccessResponse, auth=JWTAuth()
)
def update_documento_content(
    request, documento_id: int, payload: DocumentoUpdateIn, auth=None
):
    """
    Update the content of an existing document.
    Authentication is via JWT Bearer token in the Authorization header.
    """
    logger.info(f"Update documento {documento_id} request received")
    logger.info(f"Auth: {auth}")
    logger.info(f"Headers: {dict(request.headers)}")

    # Failsafe: If auth is None but there's an Authorization header, try manual token extraction and decoding
    if not auth and "Authorization" in request.headers:
        try:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
                logger.info(f"Attempting manual token decode: {token[:10]}...")

                auth = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
                logger.info(f"Manual token decode successful: {auth}")
        except Exception as e:
            logger.error(f"Manual token decode failed: {str(e)}")

    if not auth:
        logger.error("Authentication required but not provided")
        raise HttpError(401, "Authentication required")

    document_id_from_token = auth.get("document_id")
    doctor_id_from_token = auth.get("user_id")

    logger.info(
        f"Token contains: doc_id={document_id_from_token}, user_id={doctor_id_from_token}"
    )

    try:
        # Get the document and verify it exists
        documento = get_object_or_404(Documento, id=documento_id)
        logger.info(f"Found documento with id {documento_id}")

        # Verify the document belongs to the authenticated doctor
        if documento.id_medico.id != doctor_id_from_token:
            logger.warning(
                f"Permission denied: documento doctor {documento.id_medico.id} != token doctor {doctor_id_from_token}"
            )
            raise HttpError(403, "No tienes permiso para modificar este documento")

        if int(document_id_from_token) != int(documento_id):
            logger.warning(
                f"Document ID mismatch: token doc_id {document_id_from_token} != requested doc_id {documento_id}"
            )
            raise HttpError(403, "No tienes permiso para modificar este documento")

        # Update only the content field
        documento.contenido = payload.contenido
        documento.save()
        logger.info(f"Successfully updated documento {documento_id}")

        # Push event to any clients subscribed to this document
        notify_document_updated(documento_id, "transcription_complete")

        # Return simple success response
        return {
            "success": True,
            "message": f"Documento {documento_id} actualizado exitosamente",
        }
    except Http404:
        logger.error(f"Documento {documento_id} not found")
        raise HttpError(404, "Documento no encontrado")


@router.post("/notify/transcription-complete", auth=JWTAuth())
def transcription_complete_notification(
    request, payload: TranscriptionNotificationIn, auth=None
):
    """
    Endpoint for Cloud Function to notify Django about a completed transcription.
    """
    if not auth:
        logger.error("Authentication required but not provided")
        raise HttpError(401, "Authentication required")

    documento_id = payload.documento_id

    try:
        documento = get_object_or_404(Documento, id=documento_id)

        # Verify the auth token's permissions
        document_id_from_token = auth.get("document_id")
        doctor_id_from_token = auth.get("user_id")

        if int(document_id_from_token) != documento_id:
            logger.warning(
                f"Document ID mismatch: token={document_id_from_token}, requested={documento_id}"
            )
            raise HttpError(403, "Invalid document ID in token")

        if documento.id_medico.id != doctor_id_from_token:
            logger.warning(
                f"Doctor ID mismatch: doc={documento.id_medico.id}, token={doctor_id_from_token}"
            )
            raise HttpError(403, "No tienes permiso para este documento")

        # Notify any listening clients
        notify_document_updated(documento_id, "transcription_complete")

        return {
            "success": True,
            "message": f"Notificación enviada para documento {documento_id}",
        }

    except Http404:
        logger.error(f"Documento {documento_id} not found")
        raise HttpError(404, "Documento no encontrado")
