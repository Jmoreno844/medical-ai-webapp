from ninja import Router
from ninja.errors import HttpError
from django.http import Http404, StreamingHttpResponse
from django.shortcuts import get_object_or_404
import jwt
from ninja.security import django_auth

from utils.jwt_settings import get_jwt_signing_key
from utils.service_jwt import build_sse_token_payload, encode_service_jwt

from apps.documents.models import Document
from apps.documents.schemas import SSETokenResponse
from apps.documents.services.sse_hub import (
    connections_lock,
    event_queues,
)

import logging
import json
from queue import Queue, Empty

logger = logging.getLogger(__name__)
router = Router()


def _trace_id_for_log() -> str:
    try:
        from opentelemetry import trace
        from opentelemetry.trace import format_trace_id

        sc = trace.get_current_span().get_span_context()
        if sc.is_valid:
            return format_trace_id(sc.trace_id)
    except Exception:
        pass
    return ""


@router.post(
    "/generate-sse-token/{document_id}", response=SSETokenResponse, auth=django_auth
)
def generate_sse_token(request, document_id: int):
    """Generate a short-lived token for SSE connection"""
    doctor = request.user

    try:
        doc = get_object_or_404(Document, id=document_id)
        if doc.doctor.id != doctor.id:
            return {
                "success": False,
                "error": "No tienes permiso para acceder a este documento",
            }

        token = encode_service_jwt(
            build_sse_token_payload(doctor.id, document_id, minutes_ttl=5)
        )

        logger.info(
            "Generated SSE token for user %s, document %s trace_id=%s",
            doctor.id,
            document_id,
            _trace_id_for_log(),
        )
        return {"success": True, "token": token}
    except Http404:
        logger.error(f"Document {document_id} not found")
        return {"success": False, "error": "Documento no encontrado"}
    except Exception as e:
        logger.error(f"Error generating SSE token: {str(e)}")
        return {"success": False, "error": "Error interno del servidor"}


def validate_sse_token(token: str, document_id: int):
    try:
        payload = jwt.decode(token, get_jwt_signing_key(), algorithms=["HS256"])

        if payload.get("purpose") != "sse_connection":
            return False, None, "Invalid token purpose"

        token_doc_id = payload.get("document_id")
        if token_doc_id is None or int(token_doc_id) != document_id:
            return False, None, "Token doesn't match requested document"

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


@router.get("/sse/document/{document_id}/{token}")
def subscribe_to_document_updates_with_token(request, document_id: int, token: str):
    try:
        is_valid, user_id, error = validate_sse_token(token, document_id)
        if not is_valid:
            logger.warning(f"Invalid SSE token for document {document_id}: {error}")
            raise HttpError(403, error)

        doc = get_object_or_404(Document, id=document_id)
        if doc.doctor.id != user_id:
            logger.warning(
                f"Token user {user_id} doesn't match document's doctor {doc.doctor.id}"
            )
            raise HttpError(403, "No tienes permiso para acceder a este documento")

        def event_stream():
            doc_id_str = str(document_id)
            client_queue = Queue()

            with connections_lock:
                if doc_id_str not in event_queues:
                    event_queues[doc_id_str] = []
                event_queues[doc_id_str].append(client_queue)

            logger.info(
                "Client connected to SSE for document %s (token auth) trace_id=%s",
                document_id,
                _trace_id_for_log(),
            )

            yield f"data: {json.dumps({'event': 'connected', 'document_id': document_id})}\n\n"

            try:
                while True:
                    try:
                        try:
                            message = client_queue.get(timeout=30)
                            yield f"data: {message}\n\n"
                        except Empty:
                            yield ": ping\n\n"
                    except Exception as e:
                        logger.error(f"Error in SSE stream: {str(e)}")
                        break
            finally:
                with connections_lock:
                    if (
                        doc_id_str in event_queues
                        and client_queue in event_queues[doc_id_str]
                    ):
                        event_queues[doc_id_str].remove(client_queue)
                        if not event_queues[doc_id_str]:
                            del event_queues[doc_id_str]
                logger.info(
                    f"Client disconnected from SSE for document {document_id} (token auth)"
                )

        response = StreamingHttpResponse(
            event_stream(), content_type="text/event-stream"
        )

        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"

        return response

    except Http404:
        logger.error(f"Document {document_id} not found")
        raise HttpError(404, "Documento no encontrado")


@router.get("/sse/document/{document_id}", auth=django_auth)
def subscribe_to_document_updates(request, document_id: int):
    doctor = request.user
    try:
        doc = get_object_or_404(Document, id=document_id)
        if doc.doctor.id != doctor.id:
            raise HttpError(403, "No tienes permiso para acceder a este documento")

        def event_stream():
            doc_id_str = str(document_id)
            client_queue = Queue()

            with connections_lock:
                if doc_id_str not in event_queues:
                    event_queues[doc_id_str] = []
                event_queues[doc_id_str].append(client_queue)

            logger.info(
                "Client connected to SSE for document %s trace_id=%s",
                document_id,
                _trace_id_for_log(),
            )

            yield f"data: {json.dumps({'event': 'connected', 'document_id': document_id})}\n\n"

            try:
                while True:
                    try:
                        try:
                            message = client_queue.get(timeout=30)
                            yield f"data: {message}\n\n"
                        except Empty:
                            yield ": ping\n\n"
                    except Exception as e:
                        logger.error(f"Error in SSE stream: {str(e)}")
                        break
            finally:
                with connections_lock:
                    if (
                        doc_id_str in event_queues
                        and client_queue in event_queues[doc_id_str]
                    ):
                        event_queues[doc_id_str].remove(client_queue)
                        if not event_queues[doc_id_str]:
                            del event_queues[doc_id_str]
                logger.info(f"Client disconnected from SSE for document {document_id}")

        response = StreamingHttpResponse(
            event_stream(), content_type="text/event-stream"
        )

        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"

        return response

    except Http404:
        logger.error(f"Document {document_id} not found")
        raise HttpError(404, "Documento no encontrado")
