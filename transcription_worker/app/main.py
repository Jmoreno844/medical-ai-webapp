from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.auth import verify_cloud_tasks_request
from app.logging_config import configure_logging
from app.processor import Processor
from app.settings import Settings
from app.gemini import transcribe_audio
from app.text_filters import normalize_transcript

settings = Settings()
configure_logging(settings)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="VextHealth Transcription Worker",
    version="0.1.0",
    docs_url="/api/v1/docs" if settings.is_local else None,
    openapi_url="/api/v1/openapi.json" if settings.is_local else None,
)
if settings.is_local:
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
processor = Processor.create(settings)


class EmptyPayload(BaseModel):
    pass


class DebugTranscriptionResponse(BaseModel):
    success: bool
    provider: str
    model: str
    transcript: str
    content_type: str
    vad_decision: str
    vad_speech_ms: int
    vad_speech_ratio: float
    vad_error_code: str | None = None


def get_processor() -> Processor:
    return processor


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "transcription-worker"}


@app.post("/api/v1/internal/transcription/tasks/sections/{section_id}")
async def run_section_task(
    section_id: str,
    request: Request,
    _payload: EmptyPayload | None = None,
    worker: Processor = Depends(get_processor),
) -> dict[str, bool]:
    verify_cloud_tasks_request(request, settings)
    await worker.process_section(section_id)
    return {"success": True}


@app.post("/api/v1/dev/transcription/debug", response_model=DebugTranscriptionResponse)
async def debug_transcription(
    file: UploadFile = File(...),
    provider: str | None = Form(default=None),
    model: str | None = Form(default=None),
    worker: Processor = Depends(get_processor),
) -> DebugTranscriptionResponse:
    if not settings.is_local:
        raise HTTPException(status_code=404, detail="Not found")

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio file is empty")

    effective_settings = settings.model_copy(
        update={
            "transcription_provider": provider or settings.transcription_provider,
            "transcription_model": model or settings.transcription_model,
        }
    )
    vad_result = await worker._run_vad(audio_bytes)
    vad_decision = "speech"
    transcript = ""

    if not vad_result.is_speech and vad_result.error_code is None:
        vad_decision = "no_speech"
    else:
        if vad_result.error_code is not None:
            vad_decision = "fail_open"
        async with worker.gemini_semaphore:
            transcript = await transcribe_audio(
                gcs_uri=None,
                content_type=file.content_type or "audio/webm",
                settings=effective_settings,
                audio_bytes=audio_bytes,
            )
        transcript = normalize_transcript(transcript)

    return DebugTranscriptionResponse(
        success=True,
        provider=effective_settings.transcription_provider_name,
        model=effective_settings.effective_transcription_model,
        transcript=transcript,
        content_type=file.content_type or "audio/webm",
        vad_decision=vad_decision,
        vad_speech_ms=vad_result.speech_ms,
        vad_speech_ratio=vad_result.speech_ratio,
        vad_error_code=vad_result.error_code,
    )
