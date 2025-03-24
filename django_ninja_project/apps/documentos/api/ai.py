from ninja import Router
from ninja.errors import HttpError
from django.shortcuts import get_object_or_404
from django.http import Http404
from utils.auth import JWTAuth
import jwt
from django.conf import settings
from uuid import uuid4
import json
from datetime import datetime, timedelta
from ninja.security import django_auth

from apps.documentos.models import Documento
from apps.documentos.schemas import (
    DocumentoUpdateIn,
    SuccessResponse,
    TranscriptionNotificationIn,
    DocumentGenerationRequest,
    DocumentGenerationResponse,
    GenerationChunkIn,
    DocumentGenerationWorkflowRequest,
    DocumentGenerationWorkflowResponse,
)

from .sse import (
    notify_document_updated,
    notify_generation_progress,
    get_processing_id,
)

import logging
import requests
from django.conf import settings
import os
import threading

logger = logging.getLogger(__name__)
router = Router()


def get_cloud_function_url(function_name):
    """Get the URL for a cloud function from settings or environment"""
    base_url = getattr(settings, "GENERATE_DOCUMENT_CLOUD_FUNCTION_BASE_URL", None)

    if not base_url:
        base_url = os.environ.get(
            "GENERATE_DOCUMENT_CLOUD_FUNCTION_CLOUD_FUNCTION_BASE_URL"
        )

    if not base_url:
        logger.warning(
            "GENERATE_DOCUMENT_CLOUD_FUNCTION_BASE_URL not set, using localhost:8080"
        )
        base_url = "http://localhost:8080"

    return f"{base_url}/{function_name}"


@router.post("/document/generation-chunk", auth=JWTAuth())
def receive_generation_chunk(request, payload: GenerationChunkIn, auth=None):
    """
    Receive a chunk of generated content from the cloud function.
    Broadcast to connected clients and update document.
    """

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

    id_documento = payload.id_documento
    id_proceso = payload.id_proceso

    try:
        # Verify authentication and permissions
        id_documento_from_token = auth.get("id_documento")
        id_proceso_from_token = auth.get("id_proceso")

        if int(id_documento_from_token) != id_documento:
            logger.warning(
                f"Document ID mismatch: {id_documento_from_token} != {id_documento}"
            )
            raise HttpError(403, "Invalid document ID")

        if id_proceso_from_token != id_proceso:
            logger.warning(
                f"Processing ID mismatch: {id_proceso_from_token} != {id_proceso}"
            )
            raise HttpError(403, "Invalid processing ID")

        # Get the document
        documento = get_object_or_404(Documento, id=id_documento)

        # Update document content if final chunk or append if regular chunk
        if payload.is_complete:
            if payload.chunk:  # Final content provided
                documento.contenido = payload.chunk
            # Otherwise, we assume content has been updated incrementally

            # Save document
            documento.save()

            # Notify clients of completion
            notify_generation_progress(
                id_documento, id_proceso, chunk=payload.chunk, is_complete=True
            )

            return {
                "success": True,
                "message": f"Generación completada para documento {id_documento}",
            }

        elif payload.is_error:
            # Notify clients of error
            notify_generation_progress(
                id_documento,
                id_proceso,
                error=payload.error or "Error en la generación",
            )

            return {
                "success": False,
                "error": payload.error or "Error en la generación",
            }

        else:
            # Regular chunk, don't save to DB yet but notify clients
            notify_generation_progress(id_documento, id_proceso, chunk=payload.chunk)

            return {
                "success": True,
                "message": f"Chunk received for document {id_documento}",
            }

    except Http404:
        logger.error(f"Documento {id_documento} not found")
        raise HttpError(404, "Documento no encontrado")


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

    id_documento_from_token = auth.get("id_documento")  # CHANGED: from document_id
    id_medico_from_token = auth.get("id_usuario")  # CHANGED: from user_id

    logger.info(
        f"Token contains: doc_id={id_documento_from_token}, user_id={id_medico_from_token}"
    )

    try:
        # Get the document and verify it exists
        documento = get_object_or_404(Documento, id=documento_id)
        logger.info(f"Found documento with id {documento_id}")

        # Verify the document belongs to the authenticated doctor
        if documento.id_medico.id != id_medico_from_token:
            logger.warning(
                f"Permission denied: documento doctor {documento.id_medico.id} != token doctor {id_medico_from_token}"
            )
            raise HttpError(403, "No tienes permiso para modificar este documento")

        if int(id_documento_from_token) != int(documento_id):
            logger.warning(
                f"Document ID mismatch: token doc_id {id_documento_from_token} != requested doc_id {documento_id}"
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

    id_documento = payload.id_documento  # Changed from documento_id

    try:
        documento = get_object_or_404(Documento, id=id_documento)

        # Verify the auth token's permissions
        document_id_from_token = auth.get("id_documento")  # CHANGED: from document_id
        doctor_id_from_token = auth.get("id_usuario")  # CHANGED: from user_id

        if int(document_id_from_token) != id_documento:
            logger.warning(
                f"Document ID mismatch: token={document_id_from_token}, requested={id_documento}"
            )
            raise HttpError(403, "Invalid document ID in token")

        if documento.id_medico.id != doctor_id_from_token:
            logger.warning(
                f"Doctor ID mismatch: doc={documento.id_medico.id}, token={doctor_id_from_token}"
            )
            raise HttpError(403, "No tienes permiso para este documento")

        # Notify any listening clients
        notify_document_updated(id_documento, "transcription_complete")

        return {
            "success": True,
            "message": f"Notificación enviada para documento {id_documento}",
        }

    except Http404:
        logger.error(f"Documento {id_documento} not found")
        raise HttpError(404, "Documento no encontrado")


@router.post(
    "/generate-document", response=DocumentGenerationWorkflowResponse, auth=django_auth
)
def generate_document_workflow(request, data: DocumentGenerationWorkflowRequest):
    """
    Start document generation workflow combining context, transcription and template.

    1. Fetch content from the referenced documents
    2. Validate user permissions
    3. Call Cloud Function with document contents
    4. Return processing ID and SSE token to React
    """
    doctor = request.user

    try:
        # Verify permissions and fetch all required documents
        documento_contexto = get_object_or_404(Documento, id=data.id_documento_contexto)
        documento_transcripcion = get_object_or_404(
            Documento, id=data.id_documento_transcripcion
        )
        documento_nuevo = get_object_or_404(Documento, id=data.id_documento_nuevo)

        # Check if the doctor has permission for all documents
        for doc in [documento_contexto, documento_transcripcion, documento_nuevo]:
            if doc.id_medico.id != doctor.id:
                logger.warning(
                    f"Permission denied for document {doc.id}: doctor {doc.id_medico.id} != requesting doctor {doctor.id}"
                )
                raise HttpError(
                    403,
                    "No tienes permiso para acceder a uno o más documentos requeridos",
                )

        # *** ONLY VALIDATE TRANSCRIPTION DOCUMENT - Context can be empty ***
        if (
            not documento_transcripcion.contenido
            or not documento_transcripcion.contenido.strip()
        ):
            logger.error("Transcription document is empty")
            raise HttpError(
                400,
                "El documento de transcripción está vacío. Se requiere contenido para generar el documento.",
            )

        # Fetch the template doctor
        from apps.plantillas.models import PlantillaDoctor

        try:
            plantilla_doctor = PlantillaDoctor.objects.get(id=data.id_plantilla_doctor)
            # Check if template belongs to this doctor
            if plantilla_doctor.id_medico.id != doctor.id:
                raise HttpError(403, "No tienes permiso para usar esta plantilla")

            # Validate template content
            contenido_plantilla = plantilla_doctor.get_contenido_efectivo()
            if not contenido_plantilla or not contenido_plantilla.strip():
                logger.error("Template is empty")
                raise HttpError(
                    400,
                    "La plantilla seleccionada está vacía. Se requiere contenido para generar el documento.",
                )
        except PlantillaDoctor.DoesNotExist:
            raise HttpError(404, "Plantilla de doctor no encontrada")

        # Generate a processing ID
        id_proceso = get_processing_id(documento_nuevo.id)

        # Generate token for SSE connection
        sse_token = jwt.encode(
            {
                "id_documento": documento_nuevo.id,  # Changed from documento_id
                "id_usuario": doctor.id,  # Changed from user_id
                "id_proceso": id_proceso,  # Changed from processing_id
                "exp": datetime.utcnow() + timedelta(minutes=15),
                "purpose": "sse_connection",
            },
            settings.JWT_SECRET_KEY,
            algorithm="HS256",
        )

        # Generate token for cloud function authentication
        token_cloud_function = jwt.encode(
            {
                "id_documento": documento_nuevo.id,  # Changed from document_id
                "id_usuario": doctor.id,  # Changed from user_id
                "id_proceso": id_proceso,  # Changed from processing_id
                "exp": datetime.utcnow() + timedelta(minutes=30),
                "purpose": "document_generation",
            },
            settings.JWT_SECRET_KEY,
            algorithm="HS256",
        )

        # Get content and prepare the request data
        contenido_plantilla = plantilla_doctor.get_contenido_efectivo()

        # Log the content sizes before sending
        logger.info(
            f"Preparing document generation request - Content sizes: "
            f"context={len(documento_contexto.contenido)}, "
            f"transcription={len(documento_transcripcion.contenido)}, "
            f"template={len(contenido_plantilla)}"
        )

        # Prepare request data
        datos_peticion = {
            "id_documento_nuevo": documento_nuevo.id,
            "id_proceso": id_proceso,
            "documento_contexto": {
                "id": documento_contexto.id,
                "content": documento_contexto.contenido,
            },
            "documento_transcripcion": {
                "id": documento_transcripcion.id,
                "content": documento_transcripcion.contenido,
            },
            "plantilla": {
                "id": plantilla_doctor.id,
                "content": contenido_plantilla,
            },
            "auth_token": token_cloud_function,
            "validate_only": True,  # Only validate inputs, don't generate yet
        }

        # Call cloud function synchronously first to validate inputs
        url_cloud_function = get_cloud_function_url("generate_document_workflow")

        try:
            # Make a validation-only request to check if the cloud function accepts our inputs
            logger.info("Making validation request to cloud function")
            respuesta_validacion = requests.post(
                url_cloud_function,
                json=datos_peticion,
                headers={"Content-Type": "application/json"},
                timeout=10,  # Longer timeout for validation
            )

            # Check for errors in the validation response
            if respuesta_validacion.status_code != 200:
                error_msg = f"Cloud function validation failed with status {respuesta_validacion.status_code}"
                logger.error(f"{error_msg}: {respuesta_validacion.text}")
                raise HttpError(500, f"Error al validar parámetros: {error_msg}")

            try:
                response_data = respuesta_validacion.json()
                if not response_data.get("success", False):
                    error_msg = response_data.get(
                        "error", "Error desconocido en la validación"
                    )
                    logger.error(f"Cloud function validation error: {error_msg}")
                    raise HttpError(400, f"Error en los parámetros: {error_msg}")

                logger.info(
                    "Cloud function validation successful, proceeding with generation"
                )
            except json.JSONDecodeError:
                logger.error(
                    f"Invalid JSON in validation response: {respuesta_validacion.text}"
                )
                raise HttpError(500, "Error en la respuesta del servicio de validación")

        except requests.RequestException as e:
            logger.error(f"Error during validation request: {str(e)}", exc_info=True)
            raise HttpError(500, f"Error de conexión con el servicio: {str(e)}")

        # If validation succeeds, notify that generation is starting
        notify_generation_progress(
            documento_nuevo.id,
            id_proceso,
            chunk="Iniciando generación de documento...",
            is_complete=False,
        )

        # Remove validate_only flag for the actual generation
        datos_peticion["validate_only"] = False

        # Define the function for the background thread
        def call_cloud_function():
            try:
                # Make the actual generation request
                respuesta = requests.post(
                    url_cloud_function,
                    json=datos_peticion,
                    headers={"Content-Type": "application/json"},
                    timeout=5,  # Short timeout as we just need to initiate
                )

                # Handle errors in the generation response
                try:
                    response_data = respuesta.json()
                    if not response_data.get("success", True):
                        error_msg = response_data.get(
                            "error", "Error desconocido en la función"
                        )
                        logger.error(f"Cloud function generation error: {error_msg}")
                        notify_generation_progress(
                            documento_nuevo.id,
                            id_proceso,
                            error=f"Error en el servicio: {error_msg}",
                        )
                        return
                except Exception as e:
                    logger.error(f"Could not parse cloud function response: {str(e)}")

                # Check for non-200 status codes
                if respuesta.status_code != 200:
                    logger.error(f"Error calling cloud function: {respuesta.text}")
                    notify_generation_progress(
                        documento_nuevo.id,
                        id_proceso,
                        error=f"Error al iniciar generación: código {respuesta.status_code}",
                    )
                else:
                    logger.info(
                        f"Successfully initiated document generation for job {id_proceso}"
                    )

            except Exception as e:
                logger.error(f"Error calling cloud function: {str(e)}")
                notify_generation_progress(
                    documento_nuevo.id,
                    id_proceso,
                    error=f"Error al iniciar generación: {str(e)}",
                )

        # Start the background task
        hilo = threading.Thread(target=call_cloud_function)
        hilo.daemon = True
        hilo.start()

        # Return the processing ID and SSE token
        return {
            "success": True,
            "id_proceso": id_proceso,
            "sse_token": sse_token,
            "id_documento_nuevo": documento_nuevo.id,
            "message": "Generación de documento iniciada correctamente",
        }

    except Http404 as e:
        logger.error(f"Document not found: {str(e)}")
        raise HttpError(404, str(e))
    except HttpError:
        # Re-raise HttpErrors without modification
        raise
    except Exception as e:
        logger.error(f"Error starting document generation: {str(e)}", exc_info=True)
        raise HttpError(500, f"Error al iniciar la generación del documento: {str(e)}")
