from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from app.backend_client import BackendClient
from app.langsmith_tracing import LangSmithRun
from app.observability import bind_log_context, log_event
from app.pipeline.bridge import build_transcript_json
from app.pipeline.orchestrator import PIPELINE_STEP_LABELS, parse_context_inputs, run_document_pipeline
from app.settings import Settings
from document_pipeline_core.common.templates import ClinicalTemplate

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
        accumulated_markdown = ""

        template_payload = work_item.get("template")
        if not isinstance(template_payload, dict):
            raise ValueError("work_item_template_missing")
        template = ClinicalTemplate.model_validate(template_payload)

        turns_raw = work_item.get("transcription_turns")
        if not isinstance(turns_raw, list):
            raise ValueError("work_item_transcription_turns_missing")
        session_id = f"enc_{work_item['encounter_id']}"
        transcript_json = build_transcript_json(session_id=session_id, turns=turns_raw)
        context_inputs = parse_context_inputs(work_item)

        with bind_log_context(
            process_id=process_id,
            document_id=work_item["new_document_id"],
        ):
            langsmith_inputs = {
                "process_id": process_id,
                "document_id": work_item["new_document_id"],
                "encounter_id": work_item["encounter_id"],
                "turn_count": len(turns_raw),
                "section_count": len(template.sections),
            }

            loop = asyncio.get_running_loop()
            progress_queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()
            section_queue: asyncio.Queue[tuple[str, str, str]] = asyncio.Queue()

            def on_step_complete(step: str, metadata: dict[str, object]) -> None:
                loop.call_soon_threadsafe(
                    progress_queue.put_nowait,
                    (step, dict(metadata)),
                )

            def on_section_complete(section_id: str, heading: str, section_md: str) -> None:
                loop.call_soon_threadsafe(
                    section_queue.put_nowait,
                    (section_id, heading, section_md),
                )

            async def drain_queues(pipeline_task: asyncio.Task[object]) -> object:
                nonlocal emitted_chunk, accumulated_markdown
                while not pipeline_task.done() or not progress_queue.empty() or not section_queue.empty():
                    while not progress_queue.empty():
                        step, metadata = progress_queue.get_nowait()
                        log_event(
                            logger,
                            logging.INFO if self.settings.is_production else logging.DEBUG,
                            "Pipeline step completed",
                            event="pipeline_step_completed",
                            step=step,
                            **{
                                key: metadata[key]
                                for key in (
                                    "strategy",
                                    "prompt_version",
                                    "provider",
                                    "model",
                                    "duration_ms",
                                    "turn_count",
                                    "drop_count",
                                    "cluster_count",
                                    "assignment_count",
                                    "section_count",
                                    "claim_count",
                                )
                                if key in metadata
                            },
                        )
                        await self._post_progress(
                            work_item,
                            step=step,
                            message=PIPELINE_STEP_LABELS.get(step, step),
                        )
                    while not section_queue.empty():
                        _section_id, _heading, section_md = section_queue.get_nowait()
                        if accumulated_markdown:
                            accumulated_markdown = f"{accumulated_markdown}\n\n{section_md}"
                        else:
                            accumulated_markdown = section_md
                        await self._post_chunk(work_item, chunk=section_md, append=True)
                        emitted_chunk = True
                    if pipeline_task.done():
                        break
                    await asyncio.sleep(0.05)
                return pipeline_task.result()

            try:
                with LangSmithRun(
                    self.settings,
                    name="document_pipeline_worker.run_pipeline",
                    inputs=langsmith_inputs,
                    tags=["document_pipeline", "llm"],
                ) as run:
                    async with self.llm_semaphore:
                        pipeline_task = asyncio.create_task(
                            asyncio.to_thread(
                                run_document_pipeline,
                                session_id=session_id,
                                template=template,
                                transcript_json=transcript_json,
                                context_inputs=context_inputs,
                                pipeline_config=self.settings.pipeline_config,
                                on_step_complete=on_step_complete,
                                on_section_complete=on_section_complete,
                            )
                        )
                        pipeline_result = await drain_queues(pipeline_task)

                    await self._post_chunk(
                        work_item,
                        chunk=pipeline_result.document_markdown,
                        is_complete=True,
                    )
                    run.end(
                        {
                            "success": True,
                            "text_length": len(pipeline_result.document_markdown),
                            "step_count": len(pipeline_result.step_results),
                            "duration_ms": self._elapsed_ms(started_at),
                        }
                    )
            except Exception as exc:
                if not emitted_chunk:
                    log_event(
                        logger,
                        logging.ERROR,
                        "Document pipeline retryable error",
                        event="document_pipeline_retryable_error",
                        error_code=exc.__class__.__name__,
                    )
                    raise
                await self._try_post_error(
                    work_item,
                    error="Error durante la generación del documento",
                )
                log_event(
                    logger,
                    logging.ERROR,
                    "Document pipeline error after partial output",
                    event="document_pipeline_stream_error",
                    error_code=exc.__class__.__name__,
                )
                return

            log_event(
                logger,
                logging.INFO,
                "Document pipeline completed",
                event="document_pipeline_completed",
                duration_ms=self._elapsed_ms(started_at),
            )

    async def _post_progress(
        self,
        work_item: dict[str, Any],
        *,
        step: str,
        message: str,
    ) -> None:
        await self.backend.post_generation_chunk(
            callback_token=work_item["callback_token"],
            payload={
                "document_id": work_item["new_document_id"],
                "process_id": work_item["process_id"],
                "chunk": message,
                "is_progress": True,
                "pipeline_step": step,
                "is_complete": False,
                "is_error": False,
                "error": None,
            },
        )

    async def _post_chunk(
        self,
        work_item: dict[str, Any],
        *,
        chunk: str,
        is_complete: bool = False,
        append: bool = False,
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
                "append": append,
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
                "Document pipeline callback failed",
                event="document_pipeline_callback_error",
                process_id=work_item["process_id"],
                document_id=work_item["new_document_id"],
            )

    @staticmethod
    def _elapsed_ms(started_at: float) -> int:
        return int((time.monotonic() - started_at) * 1000)
