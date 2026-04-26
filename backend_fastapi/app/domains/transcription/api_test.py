from __future__ import annotations

import asyncio
import contextlib
import json
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status

from app.core.config import Settings, get_settings
from app.domains.transcription.test_realtime_stt import (
    RealtimeSpeechConfig,
    build_audio_bridge,
    stream_realtime_transcription,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _is_local_environment(environment: str) -> bool:
    return environment.strip().lower() in {"local", "dev", "development", "test", "ci"}


@router.websocket("/dev/transcription/realtime/stt")
async def realtime_stt_websocket(
    websocket: WebSocket,
    language_code: str = "es-US",
    sample_rate_hertz: int = 16_000,
    settings: Settings = Depends(get_settings),
) -> None:
    await websocket.accept()

    if not _is_local_environment(settings.environment):
        await websocket.send_json(
            {"type": "error", "error": "Realtime STT POC is only enabled locally"}
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    if not settings.gcp_project_id:
        await websocket.send_json(
            {"type": "error", "error": "GCP_PROJECT_ID is not configured"}
        )
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    speech_config = RealtimeSpeechConfig(
        project_id=settings.gcp_project_id,
        location=settings.gcp_stt_location,
        language_codes=(language_code,),
        model=settings.gcp_stt_model,
        sample_rate_hertz=sample_rate_hertz,
    )
    bridge = build_audio_bridge(speech_config)
    loop = asyncio.get_running_loop()
    stream_done = asyncio.Event()

    def send_stt_event(event: dict[str, object]) -> bool:
        future = asyncio.run_coroutine_threadsafe(websocket.send_json(event), loop)
        try:
            future.result(timeout=5)
            return True
        except Exception:
            return False

    def run_stt_stream() -> None:
        try:
            stream_realtime_transcription(bridge, speech_config, send_stt_event)
        except Exception as exc:
            logger.error("Realtime STT stream failed: %s", exc, exc_info=True)
            send_stt_event({"type": "error", "error": str(exc)})
        finally:
            loop.call_soon_threadsafe(stream_done.set)

    worker_task = asyncio.create_task(asyncio.to_thread(run_stt_stream))
    await websocket.send_json(
        {
            "type": "ready",
            "provider": "google_speech_to_text_v2",
            "audio_format": "LINEAR16_PCM_MONO",
            "sample_rate_hertz": sample_rate_hertz,
            "language_code": language_code,
            "model": settings.gcp_stt_model,
            "location": settings.gcp_stt_location,
        }
    )

    try:
        while not stream_done.is_set():
            receive_task = asyncio.create_task(websocket.receive())
            done_task = asyncio.create_task(stream_done.wait())
            done, pending = await asyncio.wait(
                {receive_task, done_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

            if done_task in done:
                break

            message = receive_task.result()
            if message["type"] == "websocket.disconnect":
                break

            audio_bytes = message.get("bytes")
            if audio_bytes is not None:
                bridge.put_audio(audio_bytes)
                continue

            text = message.get("text")
            if text is None:
                continue

            try:
                command = json.loads(text)
            except json.JSONDecodeError:
                await websocket.send_json(
                    {"type": "error", "error": "Text messages must be JSON commands"}
                )
                continue

            if command.get("type") in {"stop", "audio_stream_end"}:
                bridge.close()
                break

    except WebSocketDisconnect:
        pass
    finally:
        bridge.close()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(worker_task, timeout=10)
        with contextlib.suppress(Exception):
            await websocket.close()
