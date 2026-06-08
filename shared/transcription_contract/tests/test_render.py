from __future__ import annotations

from transcription_contract.models import ChunkTranscript, TranscriptionTurn
from transcription_contract.render import render_turns_to_clinical_text


def test_render_turns_to_clinical_text() -> None:
    chunks = [
        ChunkTranscript(
            chunk_id="1",
            start_ms=0,
            end_ms=1000,
            turns=[
                TranscriptionTurn(speaker="MEDICO", text="Buenos dias"),
                TranscriptionTurn(speaker="PACIENTE", text="Hola doctor"),
            ],
        )
    ]
    rendered = render_turns_to_clinical_text(chunks)
    assert rendered == "Médico: Buenos dias\n\nPaciente: Hola doctor"
