from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from app.backend_client import BackendClient
from app.providers import extract_clinical_facts
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
            llm_semaphore=asyncio.Semaphore(settings.clinical_extraction_max_concurrent),
        )

    async def process_session(
        self,
        session_id: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if payload and payload.get("session_id") != session_id:
            raise ValueError("session_id_mismatch")

        started_at = time.monotonic()
        work_item = await self.backend.fetch_work_item(session_id)
        try:
            async with self.llm_semaphore:
                facts = await extract_clinical_facts(
                    work_item=work_item,
                    settings=self.settings,
                )
        except Exception as exc:
            await self._try_post_result(
                session_id,
                work_item,
                {
                    "status": "failed_extraction",
                    "facts": None,
                    "raw_model_output": None,
                    "extraction_model": self.settings.effective_model,
                    "grounding_stats": None,
                    "error_code": exc.__class__.__name__,
                    "latency_ms": self._elapsed_ms(started_at),
                },
            )
            logger.warning(
                "Clinical extraction failed",
                extra={
                    "event": "clinical_extraction_failed",
                    "session_id": session_id,
                    "provider": self.settings.provider_name,
                    "model": self.settings.effective_model,
                    "error_code": exc.__class__.__name__,
                },
            )
            return

        await self.backend.post_result(
            session_id,
            callback_token=work_item["callback_token"],
            payload={
                "status": "extracted",
                "facts": facts,
                "raw_model_output": facts,
                "extraction_model": self.settings.effective_model,
                "grounding_stats": None,
                "error_code": None,
                "latency_ms": self._elapsed_ms(started_at),
            },
        )
        logger.info(
            "Clinical extraction completed",
            extra={
                "event": "clinical_extraction_completed",
                "session_id": session_id,
                "provider": self.settings.provider_name,
                "model": self.settings.effective_model,
                "duration_ms": self._elapsed_ms(started_at),
            },
        )

    async def _try_post_result(
        self,
        session_id: str,
        work_item: dict[str, Any],
        payload: dict[str, Any],
    ) -> None:
        try:
            await self.backend.post_result(
                session_id,
                callback_token=work_item["callback_token"],
                payload=payload,
            )
        except Exception:
            logger.exception(
                "Clinical extraction callback failed",
                extra={"event": "clinical_extraction_callback_failed"},
            )

    @staticmethod
    def _elapsed_ms(started_at: float) -> int:
        return int((time.monotonic() - started_at) * 1000)
