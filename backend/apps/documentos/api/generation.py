"""
Authenticated document generation workflow (Django session).
"""

import json
import logging

import requests
from django.conf import settings
from django.http import Http404
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.errors import HttpError
from ninja.security import django_auth

from apps.documentos.models import Documento
from apps.documentos.schemas import (
    DocumentGenerationWorkflowRequest,
    DocumentGenerationWorkflowResponse,
)
from apps.documentos.services.generation_runner import start_document_generation_thread
from apps.documentos.services.sse_hub import (
    get_processing_id,
    notify_generation_progress,
)
from utils.service_jwt import (
    build_generation_callback_payload,
    build_sse_token_payload,
    encode_service_jwt,
)

logger = logging.getLogger(__name__)
router = Router()


def get_generate_document_cloud_function_url() -> str:
    base_url = getattr(settings, "GENERATE_DOCUMENT_CLOUD_FUNCTION_URL", None)
    if not base_url:
        error_msg = "GENERATE_DOCUMENT_CLOUD_FUNCTION_URL setting is not configured"
        logger.error(error_msg)
        raise ValueError(error_msg)
    return f"{base_url}"


@router.post(
    "/generate-document", response=DocumentGenerationWorkflowResponse, auth=django_auth
)
def generate_document_workflow(request, data: DocumentGenerationWorkflowRequest):
    """
    Start document generation workflow combining context, transcription and template.
    """
    doctor = request.user

    try:
        documento_contexto = get_object_or_404(Documento, id=data.id_documento_contexto)
        documento_transcripcion = get_object_or_404(
            Documento, id=data.id_documento_transcripcion
        )
        documento_nuevo = get_object_or_404(Documento, id=data.id_documento_nuevo)

        for doc in [documento_contexto, documento_transcripcion, documento_nuevo]:
            if doc.id_medico.id != doctor.id:
                raise HttpError(
                    403,
                    "No tienes permiso para acceder a uno o más documentos requeridos",
                )

        if (
            not documento_transcripcion.contenido
            or not documento_transcripcion.contenido.strip()
        ):
            raise HttpError(
                400,
                "El documento de transcripción está vacío. Se requiere contenido para generar el documento.",
            )

        from apps.plantillas.models import PlantillaDoctor

        try:
            plantilla_doctor = PlantillaDoctor.objects.get(id=data.id_plantilla_doctor)
            if plantilla_doctor.id_medico.id != doctor.id:
                raise HttpError(403, "No tienes permiso para usar esta plantilla")

            contenido_plantilla = plantilla_doctor.get_contenido_efectivo()
            if not contenido_plantilla or not contenido_plantilla.strip():
                raise HttpError(
                    400,
                    "La plantilla seleccionada está vacía. Se requiere contenido para generar el documento.",
                )
        except PlantillaDoctor.DoesNotExist:
            raise HttpError(404, "Plantilla de doctor no encontrada")

        id_proceso = get_processing_id(documento_nuevo.id)

        sse_token = encode_service_jwt(
            build_sse_token_payload(
                doctor.id,
                documento_nuevo.id,
                minutes_ttl=15,
                id_proceso=id_proceso,
            )
        )

        token_cloud_function = encode_service_jwt(
            build_generation_callback_payload(
                doctor.id, documento_nuevo.id, id_proceso
            )
        )

        contenido_plantilla = plantilla_doctor.get_contenido_efectivo()

        logger.info(
            "Preparing document generation request - Content sizes: context=%s transcription=%s template=%s",
            len(documento_contexto.contenido),
            len(documento_transcripcion.contenido),
            len(contenido_plantilla),
        )

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
            "validate_only": True,
        }

        url_cloud_function = get_generate_document_cloud_function_url()

        try:
            logger.info("Making validation request to cloud function")
            respuesta_validacion = requests.post(
                url_cloud_function,
                json=datos_peticion,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )

            if respuesta_validacion.status_code != 200:
                error_msg = (
                    f"Cloud function validation failed with status "
                    f"{respuesta_validacion.status_code}"
                )
                logger.error("%s: %s", error_msg, respuesta_validacion.text)
                raise HttpError(500, f"Error al validar parámetros: {error_msg}")

            try:
                response_data = respuesta_validacion.json()
                if not response_data.get("success", False):
                    error_msg = response_data.get(
                        "error", "Error desconocido en la validación"
                    )
                    logger.error("Cloud function validation error: %s", error_msg)
                    raise HttpError(400, f"Error en los parámetros: {error_msg}")

                logger.info(
                    "Cloud function validation successful, proceeding with generation"
                )
            except json.JSONDecodeError:
                logger.error(
                    "Invalid JSON in validation response: %s",
                    respuesta_validacion.text,
                )
                raise HttpError(500, "Error en la respuesta del servicio de validación")

        except requests.RequestException as e:
            logger.error("Error during validation request: %s", e, exc_info=True)
            raise HttpError(500, f"Error de conexión con el servicio: {e}")

        notify_generation_progress(
            documento_nuevo.id,
            id_proceso,
            chunk="Iniciando generación de documento...",
            is_complete=False,
        )

        datos_peticion["validate_only"] = False

        start_document_generation_thread(
            url_cloud_function,
            datos_peticion,
            documento_nuevo.id,
            id_proceso,
        )

        return {
            "success": True,
            "id_proceso": id_proceso,
            "sse_token": sse_token,
            "id_documento_nuevo": documento_nuevo.id,
            "message": "Generación de documento iniciada correctamente",
        }

    except Http404 as e:
        logger.error("Document not found: %s", e)
        raise HttpError(404, str(e))
    except HttpError:
        raise
    except Exception as e:
        logger.error("Error starting document generation: %s", e, exc_info=True)
        raise HttpError(500, f"Error al iniciar la generación del documento: {e}")
