from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.domains.documents.sse_hub import publish_document_event
from app.integrations.http_json import JsonHttpError, post_json

logger = logging.getLogger(__name__)

CONNECT_AND_READ_TIMEOUT_SECONDS = 300.0


async def start_document_generation_task(
    *,
    url: str,
    request_body: dict[str, Any],
    document_id: int,
    process_id: str,
) -> None:
    asyncio.create_task(
        _run_generation_request(
            url=url,
            request_body=request_body,
            document_id=document_id,
            process_id=process_id,
        )
    )


async def _run_generation_request(
    *,
    url: str,
    request_body: dict[str, Any],
    document_id: int,
    process_id: str,
) -> None:
    try:
        response_data = await asyncio.to_thread(
            post_json,
            url,
            request_body,
            timeout=CONNECT_AND_READ_TIMEOUT_SECONDS,
        )
    except JsonHttpError as exc:
        logger.error("Error calling document generation cloud function: %s", exc)
        await publish_document_event(
            document_id,
            "generation_error",
            {
                "process_id": process_id,
                "error": f"Error al iniciar generación: {exc}",
                "is_error": True,
            },
        )
        return

    if response_data.get("success", True):
        logger.info("Document generation request completed for job %s", process_id)
        return

    error_msg = response_data.get("error", "Error desconocido en la función")
    logger.error("Cloud function generation error for job %s: %s", process_id, error_msg)
    await publish_document_event(
        document_id,
        "generation_error",
        {
            "process_id": process_id,
            "error": f"Error en el servicio: {error_msg}",
            "is_error": True,
        },
    )
