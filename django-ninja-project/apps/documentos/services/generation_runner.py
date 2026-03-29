"""Background HTTP kickoff for document generation Cloud Function."""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict

import requests

from apps.documentos.services.sse_hub import notify_generation_progress

logger = logging.getLogger(__name__)


def start_document_generation_thread(
    url: str,
    datos_peticion: Dict[str, Any],
    documento_id: int,
    id_proceso: str,
) -> None:
    """Fire-and-forget POST to start generation; errors reported via SSE."""

    def worker() -> None:
        try:
            respuesta = requests.post(
                url,
                json=datos_peticion,
                headers={"Content-Type": "application/json"},
                timeout=5,
            )
            try:
                response_data = respuesta.json()
                if not response_data.get("success", True):
                    error_msg = response_data.get(
                        "error", "Error desconocido en la función"
                    )
                    logger.error("Cloud function generation error: %s", error_msg)
                    notify_generation_progress(
                        documento_id,
                        id_proceso,
                        error=f"Error en el servicio: {error_msg}",
                    )
                    return
            except Exception as e:
                logger.error("Could not parse cloud function response: %s", e)

            if respuesta.status_code != 200:
                logger.error("Error calling cloud function: %s", respuesta.text)
                notify_generation_progress(
                    documento_id,
                    id_proceso,
                    error=f"Error al iniciar generación: código {respuesta.status_code}",
                )
            else:
                logger.info(
                    "Successfully initiated document generation for job %s", id_proceso
                )

        except Exception as e:
            logger.error("Error calling cloud function: %s", e)
            notify_generation_progress(
                documento_id,
                id_proceso,
                error=f"Error al iniciar generación: {e}",
            )

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
