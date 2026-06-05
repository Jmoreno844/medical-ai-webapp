from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import anyio

from app.audio import decode_audio_to_float32_pcm, download_gcs_object
from app.backend_client import BackendClient
from app.gemini import transcribe_audio
from app.observability import bind_log_context, log_event
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
        with bind_log_context(
            section_id=section_id,
            provider=self.settings.transcription_provider_name,
            model=self.settings.effective_transcription_model,
        ):
            audio_bytes = await self._download_audio_bytes(work_item["gcs_object_name"])
            vad_result = await self._run_vad(audio_bytes)

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
                log_event(
                    logger,
                    logging.INFO,
                    "Section discarded after VAD",
                    event="vad_no_speech",
                    error_code="no_speech_detected",
                    duration_ms=self._elapsed_ms(started_at),
                )
                return

            llm_started_at = time.monotonic()
            async with self.gemini_semaphore:
                transcript = await transcribe_audio(
                    gcs_uri=work_item["gcs_uri"],
                    content_type=work_item["content_type"],
                    settings=self.settings,
                    audio_bytes=audio_bytes
                    if self.settings.transcription_provider_name in {"openai", "openai_api"}
                    else None,
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
                    "transcription_provider": self.settings.transcription_provider_name,
                    "transcription_model": self.settings.effective_transcription_model,
                    "llm_latency_ms": self._elapsed_ms(llm_started_at),
                    "worker_latency_ms": self._elapsed_ms(started_at),
                },
            )
            log_event(
                logger,
                logging.INFO,
                "Section processed",
                event="section_processed",
                error_code=error_code,
                duration_ms=self._elapsed_ms(started_at),
            )

    async def _download_audio_bytes(self, gcs_object_name: str) -> bytes:
        return await anyio.to_thread.run_sync(
            download_gcs_object,
            self.settings,
            gcs_object_name,
        )

    async def _run_vad(self, audio_bytes: bytes) -> VadResult:
        try:
            async with self.vad_semaphore:
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
            log_event(
                logger,
                logging.WARNING,
                "VAD fail open",
                event="vad_fail_open",
                error_code=exc.__class__.__name__,
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
