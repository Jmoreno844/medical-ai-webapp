"""Background HTTP kickoff for document generation Cloud Function."""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict

import requests
from opentelemetry import context as otel_context

from apps.documents.services.sse_hub import notify_generation_progress

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 300


def start_document_generation_thread(
    url: str,
    request_body: Dict[str, Any],
    document_id: int,
    process_id: str,
) -> None:
    """Fire-and-forget POST to start generation; errors reported via SSE."""

    parent_ctx = otel_context.get_current()

    def worker() -> None:
        token = otel_context.attach(parent_ctx)
        try:
            # The Cloud Function performs generation inline and emits progress
            # callbacks while the HTTP request is still open. A short read
            # timeout produces false negatives even when SSE chunks are already
            # arriving in the browser.
            respuesta = requests.post(
                url,
                json=request_body,
                headers={"Content-Type": "application/json"},
                timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
            )
            try:
                response_data = respuesta.json()
                if not response_data.get("success", True):
                    error_msg = response_data.get(
                        "error", "Error desconocido en la función"
                    )
                    logger.error("Cloud function generation error: %s", error_msg)
                    notify_generation_progress(
                        document_id,
                        process_id,
                        error=f"Error en el servicio: {error_msg}",
                    )
                    return
            except Exception as e:
                logger.error("Could not parse cloud function response: %s", e)

            if respuesta.status_code != 200:
                logger.error("Error calling cloud function: %s", respuesta.text)
                notify_generation_progress(
                    document_id,
                    process_id,
                    error=f"Error al iniciar generación: código {respuesta.status_code}",
                )
            else:
                logger.info(
                    "Successfully initiated document generation for job %s", process_id
                )

        except Exception as e:
            logger.error("Error calling cloud function: %s", e)
            notify_generation_progress(
                document_id,
                process_id,
                error=f"Error al iniciar generación: {e}",
            )
        finally:
            otel_context.detach(token)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
