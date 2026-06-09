from __future__ import annotations

from app.domains.clinical_extraction.debug_mentions import (
    process_debug_clinical_mentions,
)
from app.domains.clinical_extraction.schemas import ClinicalExtractionChunk


def _chunks(*rows: tuple[str, str, str]) -> list[ClinicalExtractionChunk]:
    return [
        ClinicalExtractionChunk(
            chunk_id=chunk_id,
            section_index=0,
            speaker=speaker,
            text=text,
        )
        for chunk_id, speaker, text in rows
    ]


def test_questioned_medication_is_grounded_and_preserved() -> None:
    processed, _evidence, _stats = process_debug_clinical_mentions(
        {
            "mentions": [
                {
                    "entity_type": "medication",
                    "entity_raw": "ibuprofeno",
                    "proposition_raw": "¿Me puedo tomar ibuprofeno?",
                    "speech_act": "question",
                    "subject_role": "patient",
                    "attributes": [],
                    "evidence": [
                        {"quote": "¿Me puedo tomar ibuprofeno?", "turn_id": "s0:0"}
                    ],
                }
            ]
        },
        _chunks(("s0:0", "patient", "¿Me puedo tomar ibuprofeno?")),
    )

    mention = processed["mentions"][0]
    assert mention["entity_type"] == "medication"
    assert mention["speech_act"] == "question"


def test_instruction_to_avoid_is_preserved() -> None:
    processed, _evidence, _stats = process_debug_clinical_mentions(
        {
            "mentions": [
                {
                    "entity_type": "medication",
                    "entity_raw": "ibuprofeno",
                    "proposition_raw": "No tome ibuprofeno",
                    "speech_act": "instruction_to_avoid",
                    "subject_role": "patient",
                    "attributes": [],
                    "evidence": [{"quote": "No tome ibuprofeno", "turn_id": "s0:0"}],
                }
            ]
        },
        _chunks(("s0:0", "clinician", "No tome ibuprofeno")),
    )

    assert processed["mentions"][0]["speech_act"] == "instruction_to_avoid"


def test_pending_result_is_preserved() -> None:
    processed, _evidence, _stats = process_debug_clinical_mentions(
        {
            "mentions": [
                {
                    "entity_type": "diagnostic_test",
                    "entity_raw": "urocultivo",
                    "proposition_raw": "Se tomó el urocultivo y falta el resultado",
                    "speech_act": "pending_result",
                    "subject_role": "patient",
                    "attributes": [],
                    "evidence": [
                        {
                            "quote": "Se tomó el urocultivo y falta el resultado",
                            "turn_id": "s0:0",
                        }
                    ],
                }
            ]
        },
        _chunks(("s0:0", "clinician", "Se tomó el urocultivo y falta el resultado")),
    )

    assert processed["mentions"][0]["speech_act"] == "pending_result"


def test_atomic_split_example_survives_as_two_mentions() -> None:
    processed, _evidence, _stats = process_debug_clinical_mentions(
        {
            "mentions": [
                {
                    "entity_type": "measurement",
                    "entity_raw": "termómetro",
                    "proposition_raw": "No me he medido con termómetro",
                    "speech_act": "negation",
                    "subject_role": "patient",
                    "attributes": [],
                    "evidence": [
                        {
                            "quote": "No me he medido con termómetro",
                            "turn_id": "s0:0",
                        }
                    ],
                },
                {
                    "entity_type": "clinical_concept",
                    "entity_raw": "destemplada",
                    "proposition_raw": "me he sentido destemplada",
                    "speech_act": "assertion",
                    "subject_role": "patient",
                    "attributes": [],
                    "evidence": [
                        {
                            "quote": "me he sentido destemplada",
                            "turn_id": "s0:1",
                        }
                    ],
                },
            ]
        },
        _chunks(
            ("s0:0", "patient", "No me he medido con termómetro"),
            ("s0:1", "patient", "me he sentido destemplada"),
        ),
    )

    assert len(processed["mentions"]) == 2
    assert processed["mentions"][0]["speech_act"] == "negation"
    assert processed["mentions"][1]["speech_act"] == "assertion"


def test_unmatched_attribute_is_removed_without_dropping_mention() -> None:
    processed, _evidence, stats = process_debug_clinical_mentions(
        {
            "mentions": [
                {
                    "entity_type": "medication",
                    "entity_raw": "nitrofurantoína",
                    "proposition_raw": "Le voy a iniciar nitrofurantoína",
                    "speech_act": "prescription",
                    "subject_role": "patient",
                    "attributes": [
                        {"kind": "dose_value", "raw_text": "cien"},
                    ],
                    "evidence": [
                        {
                            "quote": "Le voy a iniciar nitrofurantoína",
                            "turn_id": "s0:0",
                        }
                    ],
                }
            ]
        },
        _chunks(("s0:0", "clinician", "Le voy a iniciar nitrofurantoína")),
    )

    assert processed["mentions"][0]["attributes"] == []
    assert stats["attributes_dropped_ungrounded"] == 1


def test_correction_requires_all_repair_attributes() -> None:
    processed, _evidence, stats = process_debug_clinical_mentions(
        {
            "mentions": [
                {
                    "entity_type": "medication",
                    "entity_raw": "Losartán",
                    "proposition_raw": "Losartán de cien, no mentiras, de cincuenta",
                    "speech_act": "correction",
                    "subject_role": "patient",
                    "attributes": [
                        {"kind": "prior_value", "raw_text": "cien"},
                        {"kind": "replacement_value", "raw_text": "cincuenta"},
                    ],
                    "evidence": [
                        {
                            "quote": "Losartán de cien, no mentiras, de cincuenta",
                            "turn_id": "s0:0",
                        }
                    ],
                }
            ]
        },
        _chunks(("s0:0", "patient", "Losartán de cien, no mentiras, de cincuenta")),
    )

    assert processed["mentions"] == []
    assert stats["correction_mentions_rejected"] == 1


def test_unmatched_quote_stays_only_in_raw_mentions() -> None:
    processed, _evidence, stats = process_debug_clinical_mentions(
        {
            "mentions": [
                {
                    "entity_type": "clinical_concept",
                    "entity_raw": "fiebre",
                    "proposition_raw": "tengo fiebre",
                    "speech_act": "assertion",
                    "subject_role": "patient",
                    "attributes": [],
                    "evidence": [{"quote": "tengo fiebre", "turn_id": "missing"}],
                }
            ]
        },
        _chunks(("s0:0", "patient", "me duele la cabeza")),
    )

    assert processed["mentions"] == []
    assert stats["mentions_dropped_unmatched"] >= 1
