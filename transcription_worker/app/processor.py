from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import anyio

from app.audio import decode_audio_to_float32_pcm, download_gcs_object
from app.backend_client import BackendClient
from app.gemini import transcribe_gcs_audio
from app.settings import Settings
from app.text_filters import normalize_transcript
from app.vad import VadResult, run_silero_vad

logger = logging.getLogger(__name__)


@dataclass
class Processor:
    settings: Settings
    backend: BackendClient
    vad_semaphore: asyncio.Semaphore
    gemini_semaphore: asyncio.Semaphore

    @classmethod
    def create(cls, settings: Settings) -> "Processor":
        return cls(
            settings=settings,
            backend=BackendClient(settings),
            vad_semaphore=asyncio.Semaphore(settings.vad_max_concurrent),
            gemini_semaphore=asyncio.Semaphore(settings.gemini_max_concurrent),
        )

    async def process_section(self, section_id: str) -> None:
        started_at = time.monotonic()
        work_item = await self.backend.get_section_work_item(section_id)
        vad_result = await self._run_vad(work_item["gcs_object_name"])

        if not vad_result.is_speech and vad_result.error_code is None:
            await self.backend.post_section_result(
                section_id,
                {
                    "status": "discarded_no_speech",
                    "transcript": "",
                    "error_code": "no_speech_detected",
                    "vad_decision": "no_speech",
                    "vad_speech_ms": vad_result.speech_ms,
                    "vad_speech_ratio": vad_result.speech_ratio,
                    "worker_latency_ms": self._elapsed_ms(started_at),
                },
            )
            logger.info(
                "vad_no_speech section_id=%s session_id=%s vad_speech_ms=%s "
                "vad_speech_ratio=%.4f",
                section_id,
                work_item["session_id"],
                vad_result.speech_ms,
                vad_result.speech_ratio,
            )
            return

        gemini_started_at = time.monotonic()
        async with self.gemini_semaphore:
            transcript = await transcribe_gcs_audio(
                gcs_uri=work_item["gcs_uri"],
                content_type=work_item["content_type"],
                settings=self.settings,
            )
        normalized = normalize_transcript(transcript)
        error_code = None if normalized else "empty_or_noise_only_transcript"
        await self.backend.post_section_result(
            section_id,
            {
                "status": "transcribed",
                "transcript": normalized,
                "error_code": error_code,
                "vad_decision": "speech"
                if vad_result.error_code is None
                else "fail_open",
                "vad_speech_ms": vad_result.speech_ms,
                "vad_speech_ratio": vad_result.speech_ratio,
                "vad_error_code": vad_result.error_code,
                "gemini_model": self.settings.transcription_gemini_model,
                "gemini_latency_ms": self._elapsed_ms(gemini_started_at),
                "worker_latency_ms": self._elapsed_ms(started_at),
            },
        )
        logger.info(
            "section_processed section_id=%s session_id=%s vad_decision=%s "
            "gemini_latency_ms=%s worker_latency_ms=%s",
            section_id,
            work_item["session_id"],
            "fail_open" if vad_result.error_code else "speech",
            self._elapsed_ms(gemini_started_at),
            self._elapsed_ms(started_at),
        )

    async def _run_vad(self, gcs_object_name: str) -> VadResult:
        try:
            async with self.vad_semaphore:
                audio_bytes = await anyio.to_thread.run_sync(
                    download_gcs_object,
                    self.settings,
                    gcs_object_name,
                )
                samples = await anyio.to_thread.run_sync(
                    decode_audio_to_float32_pcm,
                    audio_bytes,
                )
                return await anyio.to_thread.run_sync(
                    run_silero_vad,
                    samples,
                    self.settings,
                )
        except Exception as exc:
            logger.warning(
                "vad_fail_open object_name_hash=%s error_code=%s",
                hash(gcs_object_name),
                exc.__class__.__name__,
            )
            return VadResult(
                is_speech=True,
                speech_ms=0,
                speech_ratio=0.0,
                error_code="vad_error",
            )

    @staticmethod
    def _elapsed_ms(started_at: float) -> int:
        return int((time.monotonic() - started_at) * 1000)
