"""
Authenticated document generation workflow (Django session).
"""

import json
import logging
import time

import requests
from django.conf import settings
from django.http import Http404
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.errors import HttpError
from ninja.security import django_auth

from apps.documents.models import Document
from apps.documents.schemas import (
    DocumentGenerationWorkflowRequest,
    DocumentGenerationWorkflowResponse,
)
from apps.documents.services.generation_runner import start_document_generation_thread
from apps.documents.services.sse_hub import (
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
    "/documents/generate",
    response=DocumentGenerationWorkflowResponse,
    auth=django_auth,
)
def generate_document_workflow(request, data: DocumentGenerationWorkflowRequest):
    doctor = request.user

    try:
        doc_context = get_object_or_404(Document, id=data.context_document_id)
        doc_transcription = get_object_or_404(
            Document, id=data.transcription_document_id
        )
        doc_new = get_object_or_404(Document, id=data.new_document_id)

        for d in [doc_context, doc_transcription, doc_new]:
            if d.doctor.id != doctor.id:
                raise HttpError(
                    403,
                    "No tienes permiso para acceder a uno o más documentos requeridos",
                )

        if not doc_transcription.content or not doc_transcription.content.strip():
            raise HttpError(
                400,
                "El documento de transcripción está vacío. Se requiere contenido para generar el documento.",
            )

        from apps.templates.models import DoctorTemplate

        try:
            doctor_template = DoctorTemplate.objects.get(id=data.doctor_template_id)
            if doctor_template.doctor.id != doctor.id:
                raise HttpError(403, "No tienes permiso para usar esta plantilla")

            template_content = doctor_template.get_effective_content()
            if not template_content or not template_content.strip():
                raise HttpError(
                    400,
                    "La plantilla seleccionada está vacía. Se requiere contenido para generar el documento.",
                )
        except DoctorTemplate.DoesNotExist:
            raise HttpError(404, "Plantilla de doctor no encontrada")

        # Link the template to the note so its name can be used as the document title.
        doc_new.doctor_template = doctor_template
        doc_new.save(update_fields=["doctor_template"])

        process_id = get_processing_id(doc_new.id)

        sse_token = encode_service_jwt(
            build_sse_token_payload(
                doctor.id,
                doc_new.id,
                minutes_ttl=15,
                process_id=process_id,
            )
        )

        token_cloud_function = encode_service_jwt(
            build_generation_callback_payload(doctor.id, doc_new.id, process_id)
        )

        template_content = doctor_template.get_effective_content()

        logger.info(
            "Preparing document generation request - Content sizes: context=%s transcription=%s template=%s",
            len(doc_context.content),
            len(doc_transcription.content),
            len(template_content),
        )

        request_body = {
            "new_document_id": doc_new.id,
            "process_id": process_id,
            "context_document": {
                "id": doc_context.id,
                "content": doc_context.content,
            },
            "transcription_document": {
                "id": doc_transcription.id,
                "content": doc_transcription.content,
            },
            "template": {
                "id": doctor_template.id,
                "content": template_content,
            },
            "auth_token": token_cloud_function,
            "validate_only": True,
        }

        url_cloud_function = get_generate_document_cloud_function_url()

        try:
            logger.info("Making validation request to cloud function")
            validation_started_at = time.monotonic()
            validation_resp = requests.post(
                url_cloud_function,
                json=request_body,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            logger.info(
                "Cloud function validation completed in %.3f seconds with status %s",
                time.monotonic() - validation_started_at,
                validation_resp.status_code,
            )

            if validation_resp.status_code != 200:
                error_msg = (
                    f"Cloud function validation failed with status "
                    f"{validation_resp.status_code}"
                )
                logger.error("%s: %s", error_msg, validation_resp.text)
                raise HttpError(500, f"Error al validar parámetros: {error_msg}")

            try:
                response_data = validation_resp.json()
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
                    validation_resp.text,
                )
                raise HttpError(500, "Error en la respuesta del servicio de validación")

        except requests.RequestException as e:
            logger.error("Error during validation request: %s", e, exc_info=True)
            raise HttpError(500, f"Error de conexión con el servicio: {e}")

        notify_generation_progress(
            doc_new.id,
            process_id,
            chunk="Iniciando generación de documento...",
            is_complete=False,
        )

        request_body["validate_only"] = False

        start_document_generation_thread(
            url_cloud_function,
            request_body,
            doc_new.id,
            process_id,
        )

        return {
            "success": True,
            "process_id": process_id,
            "sse_token": sse_token,
            "new_document_id": doc_new.id,
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
