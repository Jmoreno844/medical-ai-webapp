from __future__ import annotations

from transcription_contract.models import ChunkTranscript, TranscriptionTurn

_SPEAKER_LABELS = {
    "MEDICO": "Médico",
    "PACIENTE": "Paciente",
    "ACOMPANANTE": "Acompañante",
    "DESCONOCIDO": "Desconocido",
}


def render_turns_to_clinical_text(chunks: list[ChunkTranscript]) -> str:
    rendered_turns: list[str] = []
    for chunk in chunks:
        for turn in chunk.turns:
            rendered = _render_turn(turn)
            if rendered:
                rendered_turns.append(rendered)
    return "\n\n".join(rendered_turns).strip()


def _render_turn(turn: TranscriptionTurn) -> str:
    text = turn.text.strip()
    if not text:
        return ""
    label = _SPEAKER_LABELS.get(turn.speaker, turn.speaker.title())
    return f"{label}: {text}"
