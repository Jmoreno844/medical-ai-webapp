from __future__ import annotations

import json
import logging

from app.audio import convert_audio_to_wav
from app.observability import log_event
from app.settings import Settings
from transcription_contract.models import TranscriptionTurn
from transcription_contract.sanitize import parse_and_sanitize_turns, parse_turns_from_response
from worker_runtime.llm.google import get_google_genai_client

SECTION_TRANSCRIPTION_SYSTEM_INSTRUCTION = """
Eres un sistema de transcripción literal y diarización de consultas médicas en español.

Transcribe únicamente lo que sea audible. No resumas, no interpretes clínicamente, no corrijas lo dicho y no completes información ausente.

REGLAS DE TURNOS

* Un turno contiene todo lo que diga consecutivamente un mismo hablante hasta que otra persona comience a hablar.
* No crees un turno nuevo por pausas, silencios breves, respiraciones, cambios de oración, enumeraciones, cifras, dosis, nombres o dictado de información.
* Si varios elementos consecutivos tienen el mismo hablante y ninguna otra persona habló entre ellos, deben quedar en un único turno.
* Crea un nuevo turno solamente cuando cambie el hablante.
* Si una persona interrumpe a otra, crea un turno separado para cada voz.
* Si el primer hablante continúa después de la interrupción, su continuación constituye un nuevo turno.
* Conserva los turnos en el orden en que comenzaron.

HABLANTES

Clasifica cada turno como MEDICO, PACIENTE, ACOMPANANTE o DESCONOCIDO.

Usa DESCONOCIDO cuando el rol no pueda determinarse con suficiente seguridad. No deduzcas un rol únicamente por el género aparente de la voz.

OVERLAP

* overlaps_previous es true cuando este hablante comenzó antes de que terminara el turno anterior.
* overlaps_next es true cuando el siguiente hablante comenzó antes de que terminara este turno.
* En ausencia de superposición, ambos valores son false.

CALIDAD

* Usa [inaudible] solamente cuando haya habla, pero una parte no sea comprensible.
* No generes texto para silencios, música o ruido.
* Si no hay habla humana inteligible, devuelve una lista turns vacía.

Ejemplo de agrupación correcta:

Una misma persona dice con pausas:
“Paciente pediátrico Juan Ríos.”
“Catorce kilos setecientos gramos.”
“Acetaminofén de ciento sesenta miligramos por cinco mililitros.”

Debe producir un único turno, no tres turnos separados.
""".strip()

SECTION_TRANSCRIPTION_USER_PROMPT = (
    "Transcribe y diariza este fragmento de audio siguiendo las instrucciones "
    "establecidas. Devuelve únicamente la respuesta estructurada."
)

SECTION_TRANSCRIPTION_JSON_SCHEMA = """
Devuelve únicamente JSON válido con este esquema:
{
  "turns": [
    {
      "speaker": "MEDICO | PACIENTE | ACOMPANANTE | DESCONOCIDO",
      "text": "texto literal",
      "overlaps_previous": false,
      "overlaps_next": false
    }
  ]
}
""".strip()

logger = logging.getLogger(__name__)


def _format_gemini_response_for_local_debug(raw_text: str) -> str:
    if not raw_text:
        return "(empty)"
    try:
        return json.dumps(json.loads(raw_text), ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        return raw_text


def _log_gemini_response_for_local_debug(
    settings: Settings,
    *,
    raw_text: str,
    model: str,
) -> None:
    if not settings.is_local:
        return
    logger.info(
        "Gemini transcription response (local debug, model=%s):\n%s",
        model,
        _format_gemini_response_for_local_debug(raw_text),
        extra={"event": "gemini_response_debug", "model": model},
    )


def _safe_int_attr(value: object, attr_name: str) -> int | None:
    raw_value = getattr(value, attr_name, None) if value is not None else None
    return raw_value if isinstance(raw_value, int) else None


def _stringify_finish_reason(value: object) -> str | None:
    if value is None:
        return None
    name = getattr(value, "name", None)
    if isinstance(name, str):
        return name
    return str(value)


def _log_gemini_response_metadata(response: object) -> None:
    candidates = getattr(response, "candidates", None) or []
    candidate = candidates[0] if candidates else None
    usage_metadata = getattr(response, "usage_metadata", None)
    log_event(
        logger,
        logging.INFO,
        "Gemini transcription response metadata",
        event="gemini_response_metadata",
        finish_reason=_stringify_finish_reason(
            getattr(candidate, "finish_reason", None) if candidate else None
        ),
        prompt_token_count=_safe_int_attr(usage_metadata, "prompt_token_count"),
        candidates_token_count=_safe_int_attr(
            usage_metadata,
            "candidates_token_count",
        ),
        thoughts_token_count=_safe_int_attr(usage_metadata, "thoughts_token_count"),
        total_token_count=_safe_int_attr(usage_metadata, "total_token_count"),
    )


def _get_google_client(project_id: str, location: str):
    return get_google_genai_client(project_id, location)


async def transcribe_audio(
    *,
    gcs_uri: str | None,
    content_type: str,
    settings: Settings,
    audio_bytes: bytes | None = None,
) -> list[TranscriptionTurn]:
    raw_text = await _transcribe_with_google(
        gcs_uri=gcs_uri,
        content_type=content_type,
        settings=settings,
        audio_bytes=audio_bytes,
    )
    return parse_and_sanitize_turns(raw_text)


async def transcribe_audio_raw_turns(
    *,
    gcs_uri: str | None,
    content_type: str,
    settings: Settings,
    audio_bytes: bytes | None = None,
) -> list[TranscriptionTurn]:
    raw_text = await _transcribe_with_google(
        gcs_uri=gcs_uri,
        content_type=content_type,
        settings=settings,
        audio_bytes=audio_bytes,
    )
    return parse_turns_from_response(raw_text)


async def _transcribe_with_google(
    *,
    gcs_uri: str | None,
    content_type: str,
    settings: Settings,
    audio_bytes: bytes | None = None,
) -> list[TranscriptionTurn]:
    from google.genai import types

    if not settings.gcp_project_id:
        raise ValueError("GCP_PROJECT_ID is required")
    client = _get_google_client(settings.gcp_project_id, settings.vertex_ai_location)
    inline_bytes = audio_bytes
    inline_content_type = content_type
    if audio_bytes is not None and gcs_uri is None:
        inline_bytes = convert_audio_to_wav(audio_bytes)
        inline_content_type = "audio/wav"
    audio_part = (
        types.Part.from_uri(file_uri=gcs_uri, mime_type=content_type)
        if gcs_uri
        else types.Part.from_bytes(
            data=inline_bytes or b"",
            mime_type=inline_content_type,
        )
    )
    response = await client.aio.models.generate_content(
        model=settings.effective_transcription_model,
        contents=[
            types.Part.from_text(text=SECTION_TRANSCRIPTION_USER_PROMPT),
            audio_part,
        ],
        config=types.GenerateContentConfig(
            system_instruction=(
                f"{SECTION_TRANSCRIPTION_SYSTEM_INSTRUCTION}\n\n"
                f"{SECTION_TRANSCRIPTION_JSON_SCHEMA}"
            ),
            temperature=0.0,
            top_p=0.1,
            candidate_count=1,
            max_output_tokens=settings.transcription_gemini_max_output_tokens,
            response_mime_type="application/json",
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    raw_text = getattr(response, "text", "") or ""
    _log_gemini_response_metadata(response)
    _log_gemini_response_for_local_debug(
        settings,
        raw_text=raw_text,
        model=settings.effective_transcription_model,
    )
    return raw_text
