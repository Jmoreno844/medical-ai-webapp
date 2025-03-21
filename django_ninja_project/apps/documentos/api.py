from typing import List
from ninja import Router
from ninja.errors import HttpError
from django.shortcuts import get_object_or_404
from django.http import Http404, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt

from ninja.security import django_auth
from utils.auth import JWTAuth
import jwt

from django.conf import settings
from datetime import datetime, timedelta

from apps.documentos.models import Documento
from apps.documentos.schemas import (
    DocumentoIn,
    DocumentoOut,
    DocumentoUpdateIn,
    SuccessResponse,
    DocumentoContentOut,
    TranscriptionNotificationIn,
    SSETokenResponse,
)
from apps.encuentro.models import Encuentro

import logging
import threading
import json
import asyncio
import time
from queue import Queue

logger = logging.getLogger(__name__)
router = Router()

# Dictionary to store active SSE connections by document ID
sse_clients = {}
connections_lock = threading.Lock()

# Queue for events
event_queues = {}


@router.post("/documento", response=DocumentoOut, auth=django_auth)
def create_documento(request, payload: DocumentoIn):
    """
    Create a new documento. If tipo is 'plantilla', id_plantilla_doctor is required.
    """
    # Get the authenticated doctor
    doctor = request.user  # Change from request.auth to request.user

    # Verify the encounter exists and belongs to this doctor
    try:
        encuentro = Encuentro.objects.get(id=payload.id_encuentro)
        if encuentro.id_medico.id != doctor.id:
            raise HttpError(403, "No tienes permiso para acceder a este encuentro")
    except Encuentro.DoesNotExist:
        raise HttpError(404, "Encuentro no encontrado")

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
        id_plantilla_doctor_id=payload.id_plantilla_doctor
        if payload.id_plantilla_doctor
        else None,
        contenido=payload.contenido,
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


def notify_document_updated(documento_id, event_type):
    """Send an event to any clients subscribed to this document"""
    doc_id_str = str(documento_id)

    with connections_lock:
        if doc_id_str in event_queues:
            event_data = {
                "event": event_type,
                "documento_id": documento_id,
                "timestamp": datetime.now().isoformat(),
            }

            for queue in event_queues[doc_id_str]:
                queue.put(json.dumps(event_data))

            logger.info(
                f"Sent {event_type} event to {len(event_queues[doc_id_str])} clients for document {documento_id}"
            )


@router.post(
    "/generate-sse-token/{documento_id}", response=SSETokenResponse, auth=django_auth
)
def generate_sse_token(request, documento_id: int):
    """Generate a short-lived token for SSE connection"""
    doctor = request.user

    try:
        # Verify permissions
        documento = get_object_or_404(Documento, id=documento_id)
        if documento.id_medico.id != doctor.id:
            return {
                "success": False,
                "error": "No tienes permiso para acceder a este documento",
            }

        # Generate a short-lived token (5 minutes)
        token = jwt.encode(
            {
                "documento_id": documento_id,
                "user_id": doctor.id,
                "exp": datetime.utcnow() + timedelta(minutes=5),
                "purpose": "sse_connection",
            },
            settings.JWT_SECRET_KEY,
            algorithm="HS256",
        )

        logger.info(
            f"Generated SSE token for user {doctor.id}, documento {documento_id}"
        )
        return {"success": True, "token": token}
    except Http404:
        logger.error(f"Documento {documento_id} not found")
        return {"success": False, "error": "Documento no encontrado"}
    except Exception as e:
        logger.error(f"Error generating SSE token: {str(e)}")
        return {"success": False, "error": "Error interno del servidor"}


def validate_sse_token(token: str, documento_id: int):
    """
    Validate an SSE token for a specific document.
    Returns (is_valid, user_id, error_message)
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])

        # Check token purpose
        if payload.get("purpose") != "sse_connection":
            return False, None, "Invalid token purpose"

        # Check document ID
        token_doc_id = payload.get("documento_id")
        if token_doc_id is None or int(token_doc_id) != documento_id:
            return False, None, "Token doesn't match requested document"

        # Get user ID
        user_id = payload.get("user_id")
        if not user_id:
            return False, None, "Missing user ID in token"

        return True, user_id, None

    except jwt.ExpiredSignatureError:
        return False, None, "Token expired"
    except jwt.InvalidTokenError as e:
        return False, None, f"Invalid token: {str(e)}"
    except Exception as e:
        logger.error(f"Error validating SSE token: {str(e)}")
        return False, None, "Token validation error"


@router.get("/sse/documento/{documento_id}/{token}")
def subscribe_to_document_updates_with_token(request, documento_id: int, token: str):
    """
    Server-Sent Events endpoint for subscribing to document updates using JWT token.
    """
    try:
        # Validate token
        is_valid, user_id, error = validate_sse_token(token, documento_id)
        if not is_valid:
            logger.warning(f"Invalid SSE token for document {documento_id}: {error}")
            raise HttpError(403, error)

        # Verify document exists and belongs to this user
        documento = get_object_or_404(Documento, id=documento_id)
        if documento.id_medico.id != user_id:
            logger.warning(
                f"Token user {user_id} doesn't match document's doctor {documento.id_medico.id}"
            )
            raise HttpError(403, "No tienes permiso para acceder a este documento")

        # Use the same event stream logic as the original endpoint
        def event_stream():
            """SSE event generator"""
            doc_id_str = str(documento_id)
            client_queue = Queue()

            # Register this client
            with connections_lock:
                if doc_id_str not in event_queues:
                    event_queues[doc_id_str] = []
                event_queues[doc_id_str].append(client_queue)

            logger.info(
                f"Client connected to SSE for document {documento_id} (token auth)"
            )

            # Send initial connection event
            yield f"data: {json.dumps({'event': 'connected', 'documento_id': documento_id})}\n\n"

            try:
                while True:
                    try:
                        # Check for messages or timeout after 30 seconds
                        try:
                            message = client_queue.get(timeout=30)
                            yield f"data: {message}\n\n"
                        except Queue.Empty:
                            # Send keep-alive comment
                            yield ": ping\n\n"
                    except Exception as e:
                        logger.error(f"Error in SSE stream: {str(e)}")
                        break
            finally:
                # Remove client when connection closes
                with connections_lock:
                    if (
                        doc_id_str in event_queues
                        and client_queue in event_queues[doc_id_str]
                    ):
                        event_queues[doc_id_str].remove(client_queue)
                        if not event_queues[doc_id_str]:
                            del event_queues[doc_id_str]
                logger.info(
                    f"Client disconnected from SSE for document {documento_id} (token auth)"
                )

        response = StreamingHttpResponse(
            event_stream(), content_type="text/event-stream"
        )

        # Disable buffering in middleware
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"

        return response

    except Http404:
        logger.error(f"Documento {documento_id} not found")
        raise HttpError(404, "Documento no encontrado")


# Keep existing endpoint for backward compatibility
@router.get("/sse/documento/{documento_id}", auth=django_auth)
def subscribe_to_document_updates(request, documento_id: int):
    """
    Server-Sent Events endpoint for subscribing to document updates.
    Uses Django authentication.
    """
    doctor = request.user
    try:
        # Verify permissions for this document
        documento = get_object_or_404(Documento, id=documento_id)
        if documento.id_medico.id != doctor.id:
            raise HttpError(403, "No tienes permiso para acceder a este documento")

        def event_stream():
            """SSE event generator"""
            doc_id_str = str(documento_id)
            client_queue = Queue()

            # Register this client
            with connections_lock:
                if doc_id_str not in event_queues:
                    event_queues[doc_id_str] = []
                event_queues[doc_id_str].append(client_queue)

            logger.info(f"Client connected to SSE for document {documento_id}")

            # Send initial connection event
            yield f"data: {json.dumps({'event': 'connected', 'documento_id': documento_id})}\n\n"

            try:
                while True:
                    try:
                        # Check for messages or timeout after 30 seconds
                        try:
                            message = client_queue.get(timeout=30)
                            yield f"data: {message}\n\n"
                        except Queue.Empty:
                            # Send keep-alive comment
                            yield ": ping\n\n"
                    except Exception as e:
                        logger.error(f"Error in SSE stream: {str(e)}")
                        break
            finally:
                # Remove client when connection closes
                with connections_lock:
                    if (
                        doc_id_str in event_queues
                        and client_queue in event_queues[doc_id_str]
                    ):
                        event_queues[doc_id_str].remove(client_queue)
                        if not event_queues[doc_id_str]:
                            del event_queues[doc_id_str]
                logger.info(f"Client disconnected from SSE for document {documento_id}")

        response = StreamingHttpResponse(
            event_stream(), content_type="text/event-stream"
        )

        # Disable buffering in middleware
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"

        return response

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
