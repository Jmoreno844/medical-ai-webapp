from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from app.backend_client import BackendClient
from app.langsmith_tracing import LangSmithRun
from app.llm import stream_document_generation
from app.observability import bind_log_context, log_event
from app.prompts import build_document_prompt
from app.settings import Settings

logger = logging.getLogger(__name__)


@dataclass
class Processor:
    settings: Settings
    backend: BackendClient
    llm_semaphore: asyncio.Semaphore

    @classmethod
    def create(cls, settings: Settings) -> "Processor":
        return cls(
            settings=settings,
            backend=BackendClient(settings),
            llm_semaphore=asyncio.Semaphore(settings.llm_max_concurrent),
        )

    async def process_task(self, process_id: str, payload: dict[str, Any]) -> None:
        if payload.get("process_id") != process_id:
            raise ValueError("process_id_mismatch")

        started_at = time.monotonic()
        work_item = await self.backend.fetch_work_item(process_id, payload)
        emitted_chunk = False
        complete_text = ""
        buffer = ""
        llm_started_at = time.monotonic()

        with bind_log_context(
            process_id=process_id,
            document_id=work_item["new_document_id"],
            provider=self.settings.document_generation_provider_name,
            model=self.settings.effective_document_generation_model,
        ):
            prompt = build_document_prompt(
                template_content=work_item["template_content"],
                context_content=work_item["context_content"],
                transcription_content=work_item["transcription_content"],
            )
            langsmith_inputs = {
                "process_id": process_id,
                "document_id": work_item["new_document_id"],
                "encounter_id": work_item["encounter_id"],
                "doctor_template_id": work_item["doctor_template_id"],
                "template_length": len(work_item["template_content"] or ""),
                "context_length": len(work_item["context_content"] or ""),
                "transcription_length": len(work_item["transcription_content"] or ""),
                "provider": self.settings.document_generation_provider_name,
                "model": self.settings.effective_document_generation_model,
            }

            try:
                with LangSmithRun(
                    self.settings,
                    name="document_generation_worker.generate_document",
                    inputs=langsmith_inputs,
                    tags=["document_generation", "llm", self.settings.document_generation_provider_name],
                ) as run:
                    async with self.llm_semaphore:
                        async for chunk in stream_document_generation(
                            prompt=prompt,
                            settings=self.settings,
                        ):
                            complete_text += chunk
                            buffer += chunk
                            if len(buffer) >= self.settings.chunk_size:
                                await self._post_chunk(work_item, chunk=buffer)
                                emitted_chunk = True
                                buffer = ""

                    if buffer:
                        await self._post_chunk(work_item, chunk=buffer)
                        emitted_chunk = True

                    await self._post_chunk(
                        work_item,
                        chunk=complete_text,
                        is_complete=True,
                    )
                    run.end(
                        {
                            "success": True,
                            "provider": self.settings.document_generation_provider_name,
                            "model": self.settings.effective_document_generation_model,
                            "text_length": len(complete_text),
                            "llm_latency_ms": self._elapsed_ms(llm_started_at),
                        }
                    )
            except Exception as exc:
                if not emitted_chunk:
                    log_event(
                        logger,
                        logging.ERROR,
                        "Document generation retryable error",
                        event="document_generation_retryable_error",
                        error_code=exc.__class__.__name__,
                    )
                    raise
                await self._try_post_error(
                    work_item,
                    error="Error durante la generacion del documento",
                )
                log_event(
                    logger,
                    logging.ERROR,
                    "Document generation stream error",
                    event="document_generation_stream_error",
                    error_code=exc.__class__.__name__,
                )
                return

            log_event(
                logger,
                logging.INFO,
                "Document generation completed",
                event="document_generated",
                duration_ms=self._elapsed_ms(started_at),
            )

    async def _post_chunk(
        self,
        work_item: dict[str, Any],
        *,
        chunk: str,
        is_complete: bool = False,
    ) -> None:
        await self.backend.post_generation_chunk(
            callback_token=work_item["callback_token"],
            payload={
                "document_id": work_item["new_document_id"],
                "process_id": work_item["process_id"],
                "chunk": chunk,
                "is_complete": is_complete,
                "is_error": False,
                "error": None,
            },
        )

    async def _try_post_error(self, work_item: dict[str, Any], *, error: str) -> None:
        try:
            await self.backend.post_generation_chunk(
                callback_token=work_item["callback_token"],
                payload={
                    "document_id": work_item["new_document_id"],
                    "process_id": work_item["process_id"],
                    "chunk": "",
                    "is_complete": False,
                    "is_error": True,
                    "error": error,
                },
            )
        except Exception:
            log_event(
                logger,
                logging.ERROR,
                "Document generation callback failed",
                event="document_generation_callback_error",
                process_id=work_item["process_id"],
                document_id=work_item["new_document_id"],
            )

    @staticmethod
    def _elapsed_ms(started_at: float) -> int:
        return int((time.monotonic() - started_at) * 1000)
