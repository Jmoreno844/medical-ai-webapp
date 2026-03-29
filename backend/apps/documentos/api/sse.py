from ninja import Router
from ninja.errors import HttpError
from django.http import Http404, StreamingHttpResponse
from django.shortcuts import get_object_or_404
import jwt
from ninja.security import django_auth

from utils.jwt_settings import get_jwt_signing_key
from utils.service_jwt import build_sse_token_payload, encode_service_jwt

from apps.documentos.models import Documento
from apps.documentos.schemas import SSETokenResponse
from apps.documentos.services.sse_hub import (
    connections_lock,
    event_queues,
)

import logging
import json
from queue import Queue

logger = logging.getLogger(__name__)
router = Router()


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

        token = encode_service_jwt(
            build_sse_token_payload(doctor.id, documento_id, minutes_ttl=5)
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
        payload = jwt.decode(token, get_jwt_signing_key(), algorithms=["HS256"])

        # Check token purpose
        if payload.get("purpose") != "sse_connection":
            return False, None, "Invalid token purpose"

        # Check document ID
        token_doc_id = payload.get("id_documento")  # Changed from documento_id
        if token_doc_id is None or int(token_doc_id) != documento_id:
            return False, None, "Token doesn't match requested document"

        # Get user ID
        user_id = payload.get("id_usuario")  # Changed from user_id
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
