from __future__ import annotations

from transcription_contract.merge import merge_consecutive_turns
from transcription_contract.models import TranscriptionTurn


def _turn(
    speaker: str,
    text: str,
    *,
    overlaps_previous: bool = False,
    overlaps_next: bool = False,
) -> TranscriptionTurn:
    return TranscriptionTurn(
        speaker=speaker,
        text=text,
        overlaps_previous=overlaps_previous,
        overlaps_next=overlaps_next,
    )


def test_merge_consecutive_same_speaker_fragments() -> None:
    turns = [
        _turn("MEDICO", "Paciente pediátrico Yanga él Ríos."),
        _turn("MEDICO", "Son Panzi."),
        _turn("MEDICO", "14 kg 700 gramos."),
        _turn("MEDICO", "Hace de 160 mg por 5 ml."),
    ]

    merged = merge_consecutive_turns(turns)

    assert len(merged) == 1
    assert merged[0].speaker == "MEDICO"
    assert merged[0].text == (
        "Paciente pediátrico Yanga él Ríos. Son Panzi. "
        "14 kg 700 gramos. Hace de 160 mg por 5 ml."
    )


def test_merge_does_not_combine_overlapping_turns() -> None:
    turns = [
        _turn(
            "MEDICO",
            "Debe tomarlo cada ocho horas.",
            overlaps_next=True,
        ),
        _turn(
            "PACIENTE",
            "¿También en la madrugada?",
            overlaps_previous=True,
        ),
    ]

    merged = merge_consecutive_turns(turns)

    assert len(merged) == 2
    assert merged[0].text == "Debe tomarlo cada ocho horas."
    assert merged[1].text == "¿También en la madrugada?"


def test_merge_keeps_new_turn_after_interruption_by_other_speaker() -> None:
    turns = [
        _turn("MEDICO", "¿Cómo se llama?"),
        _turn("PACIENTE", "Se llama Juan."),
        _turn("MEDICO", "Perfecto."),
    ]

    merged = merge_consecutive_turns(turns)

    assert len(merged) == 3
    assert [turn.speaker for turn in merged] == ["MEDICO", "PACIENTE", "MEDICO"]


def test_merge_skips_empty_turns_before_evaluating() -> None:
    turns = [
        _turn("MEDICO", "Hola."),
        _turn("MEDICO", "   "),
        _turn("MEDICO", "Adiós."),
    ]

    merged = merge_consecutive_turns(turns)

    assert len(merged) == 1
    assert merged[0].text == "Hola. Adiós."


def test_merge_propagates_overlaps_next_to_previous() -> None:
    turns = [
        _turn("MEDICO", "Primera parte."),
        _turn("MEDICO", "Segunda parte.", overlaps_next=True),
    ]

    merged = merge_consecutive_turns(turns)

    assert len(merged) == 1
    assert merged[0].text == "Primera parte. Segunda parte."
    assert merged[0].overlaps_next is True
