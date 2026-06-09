from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.domains.clinical_extraction.service import (
    _build_extraction_chunks,
    process_clinical_facts,
)


def _recording_session() -> SimpleNamespace:
    return SimpleNamespace(
        encounter_id=10,
        document_id=20,
        doctor_id=30,
        encounter=SimpleNamespace(
            occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            patient=SimpleNamespace(id=40, name="Paciente"),
        ),
    )


def _common_claim_fields(**overrides: object) -> dict:
    return {
        "information_source_role": "patient",
        "subject_role": "patient",
        "assertion": "present",
        "claim_lifecycle": "active",
        "reported_certainty": None,
        **overrides,
    }


def _process(facts: dict, transcript: dict):
    chunks = _build_extraction_chunks(transcript)
    return process_clinical_facts(
        facts,
        chunks,
        recording_session=_recording_session(),  # type: ignore[arg-type]
    )


def _warnings(processed: dict) -> list[str]:
    return processed["data_quality"]["extraction_warnings"]


def test_subject_raw_text_me_headache_becomes_null() -> None:
    processed, _evidence, _stats = _process(
        {
            "clinical_events": [
                {
                    "concept_raw_text": "dolor de cabeza",
                    "text_raw": None,
                    "value_raw": None,
                    "unit_raw": None,
                    "event_kind": "symptom",
                    "body_site_raw": "cabeza",
                    "laterality_raw": None,
                    "severity_raw": None,
                    "onset_raw": None,
                    "duration_raw": None,
                    "time_expression_raw": None,
                    "name_raw": None,
                    "dose_value": None,
                    "dose_unit": None,
                    "route_raw": None,
                    "frequency_raw": None,
                    "timing_raw": None,
                    "exposure_duration_raw": None,
                    "prescribed_duration_raw": None,
                    "adherence_raw": None,
                    "substance_raw": None,
                    "reaction_raw": None,
                    "category": None,
                    "result_content_raw": None,
                    "type_raw": None,
                    "execution_status": None,
                    "reason_raw": None,
                    "conditional_on_raw_text": None,
                    "evidence": [
                        {
                            "quote": "Me duele la cabeza",
                            "supports_fields": ["concept_raw_text", "body_site_raw"],
                            "chunk_hint": "s0:0",
                        }
                    ],
                    **_common_claim_fields(
                        subject_role="patient",
                        subject_raw_text="Me",
                    ),
                }
            ]
        },
        {
            "chunks": [
                {
                    "chunk_id": "s0",
                    "turns": [{"speaker": "PACIENTE", "text": "Me duele la cabeza"}],
                }
            ]
        },
    )

    event = processed["clinical_events"][0]
    assert event["subject_raw_text"] is None
    assert event["subject_role"] == "patient"
    assert any("subject_raw_text_not_explicit" in warning for warning in _warnings(processed))


def test_subject_raw_text_toma_medication_preserved() -> None:
    processed, _evidence, _stats = _process(
        {
            "medications": [
                {
                    "name_raw": "losartán",
                    "dose_value": None,
                    "dose_unit": None,
                    "route_raw": None,
                    "frequency_raw": None,
                    "timing_raw": None,
                    "exposure_duration_raw": None,
                    "prescribed_duration_raw": None,
                    "adherence_raw": None,
                    "evidence": [
                        {
                            "quote": "Toma losartán",
                            "supports_fields": ["name_raw"],
                            "chunk_hint": "s0:0",
                        }
                    ],
                    **_common_claim_fields(subject_raw_text="Toma"),
                }
            ]
        },
        {
            "chunks": [
                {
                    "chunk_id": "s0",
                    "turns": [{"speaker": "PACIENTE", "text": "Toma losartán"}],
                }
            ]
        },
    )

    medication = processed["medications"][0]
    assert medication["subject_raw_text"] is None
    assert medication["name_raw"] == "losartán"
    assert any("subject_raw_text_not_explicit" in warning for warning in _warnings(processed))


def test_subject_raw_text_mi_mama_preserved() -> None:
    processed, _evidence, _stats = _process(
        {
            "history": {
                "family_history": [
                    {
                        "concept_raw_text": "diabetes",
                        "text_raw": None,
                        "value_raw": None,
                        "unit_raw": None,
                        "event_kind": None,
                        "body_site_raw": None,
                        "laterality_raw": None,
                        "severity_raw": None,
                        "onset_raw": None,
                        "duration_raw": None,
                        "time_expression_raw": None,
                        "name_raw": None,
                        "dose_value": None,
                        "dose_unit": None,
                        "route_raw": None,
                        "frequency_raw": None,
                        "timing_raw": None,
                        "exposure_duration_raw": None,
                        "prescribed_duration_raw": None,
                        "adherence_raw": None,
                        "substance_raw": None,
                        "reaction_raw": None,
                        "category": None,
                        "result_content_raw": None,
                        "type_raw": None,
                        "execution_status": None,
                        "reason_raw": None,
                        "conditional_on_raw_text": None,
                        "evidence": [
                            {
                                "quote": "Mi mamá tiene diabetes",
                                "supports_fields": [
                                    "concept_raw_text",
                                    "subject_raw_text",
                                ],
                                "chunk_hint": "s0:0",
                            }
                        ],
                        **_common_claim_fields(
                            subject_role="family_member",
                            subject_raw_text="mi mamá",
                        ),
                    }
                ],
                "conditions": [],
                "surgeries_and_procedures": [],
                "trauma": [],
                "gynecologic_obstetric": [],
                "social_history": [],
                "exposures": [],
                "unclassified_explicit_history_facts": [],
            }
        },
        {
            "chunks": [
                {
                    "chunk_id": "s0",
                    "turns": [
                        {"speaker": "PACIENTE", "text": "Mi mamá tiene diabetes"}
                    ],
                }
            ]
        },
    )

    fact = processed["history"]["family_history"][0]
    assert fact["subject_raw_text"] == "mi mamá"
    assert not any(
        "subject_raw_text_not_explicit" in warning
        for warning in _warnings(processed)
    )


def test_subject_raw_text_paciente_not_in_quote_becomes_null() -> None:
    processed, _evidence, _stats = _process(
        {
            "clinical_events": [
                {
                    "concept_raw_text": "fiebre",
                    "text_raw": None,
                    "value_raw": None,
                    "unit_raw": None,
                    "event_kind": "symptom",
                    "body_site_raw": None,
                    "laterality_raw": None,
                    "severity_raw": None,
                    "onset_raw": None,
                    "duration_raw": None,
                    "time_expression_raw": None,
                    "name_raw": None,
                    "dose_value": None,
                    "dose_unit": None,
                    "route_raw": None,
                    "frequency_raw": None,
                    "timing_raw": None,
                    "exposure_duration_raw": None,
                    "prescribed_duration_raw": None,
                    "adherence_raw": None,
                    "substance_raw": None,
                    "reaction_raw": None,
                    "category": None,
                    "result_content_raw": None,
                    "type_raw": None,
                    "execution_status": None,
                    "reason_raw": None,
                    "conditional_on_raw_text": None,
                    "evidence": [
                        {
                            "quote": "Tuve fiebre anoche",
                            "supports_fields": ["concept_raw_text", "subject_raw_text"],
                            "chunk_hint": "s0:0",
                        }
                    ],
                    **_common_claim_fields(
                        subject_role="patient",
                        subject_raw_text="paciente",
                    ),
                }
            ]
        },
        {
            "chunks": [
                {
                    "chunk_id": "s0",
                    "turns": [{"speaker": "PACIENTE", "text": "Tuve fiebre anoche"}],
                }
            ]
        },
    )

    assert processed["clinical_events"][0]["subject_raw_text"] is None


def test_subject_raw_text_accepts_case_and_punctuation_differences() -> None:
    processed, _evidence, _stats = _process(
        {
            "clinical_events": [
                {
                    "concept_raw_text": "fiebre",
                    "text_raw": None,
                    "value_raw": None,
                    "unit_raw": None,
                    "event_kind": "symptom",
                    "body_site_raw": None,
                    "laterality_raw": None,
                    "severity_raw": None,
                    "onset_raw": None,
                    "duration_raw": None,
                    "time_expression_raw": None,
                    "name_raw": None,
                    "dose_value": None,
                    "dose_unit": None,
                    "route_raw": None,
                    "frequency_raw": None,
                    "timing_raw": None,
                    "exposure_duration_raw": None,
                    "prescribed_duration_raw": None,
                    "adherence_raw": None,
                    "substance_raw": None,
                    "reaction_raw": None,
                    "category": None,
                    "result_content_raw": None,
                    "type_raw": None,
                    "execution_status": None,
                    "reason_raw": None,
                    "conditional_on_raw_text": None,
                    "evidence": [
                        {
                            "quote": "El paciente, tuvo fiebre anoche.",
                            "supports_fields": ["concept_raw_text", "subject_raw_text"],
                            "chunk_hint": "s0:0",
                        }
                    ],
                    **_common_claim_fields(
                        subject_role="patient",
                        subject_raw_text="el paciente",
                    ),
                }
            ]
        },
        {
            "chunks": [
                {
                    "chunk_id": "s0",
                    "turns": [
                        {
                            "speaker": "PACIENTE",
                            "text": "El paciente, tuvo fiebre anoche.",
                        }
                    ],
                }
            ]
        },
    )

    assert processed["clinical_events"][0]["subject_raw_text"] == "el paciente"


def test_summary_none_reported_without_evidence_degrades() -> None:
    processed, _evidence, stats = _process(
        {
            "allergy_summary": {
                "assertion": "none_reported",
                "scope_raw_text": None,
                "evidence": [],
            }
        },
        {"chunks": []},
    )

    summary = processed["allergy_summary"]
    assert summary["assertion"] is None
    assert summary["scope_raw_text"] is None
    assert summary["evidence"] == []
    assert stats["validation_warnings"] >= 1
    assert any(
        "collection_summary_none_reported_without_explicit_evidence" in warning
        for warning in _warnings(processed)
    )


def test_summary_none_reported_unmatched_quote_degrades() -> None:
    processed, _evidence, _stats = _process(
        {
            "allergy_summary": {
                "assertion": "none_reported",
                "scope_raw_text": None,
                "evidence": [
                    {
                        "quote": "No tengo alergias inventadas",
                        "supports_fields": ["assertion"],
                        "chunk_hint": "missing:0",
                    }
                ],
            }
        },
        {
            "chunks": [
                {
                    "chunk_id": "s0",
                    "turns": [{"speaker": "PACIENTE", "text": "No tengo alergias"}],
                }
            ]
        },
    )

    assert processed["allergy_summary"]["assertion"] is None


def test_summary_none_reported_ambiguous_quote_degrades() -> None:
    processed, _evidence, _stats = _process(
        {
            "allergy_summary": {
                "assertion": "none_reported",
                "scope_raw_text": None,
                "evidence": [
                    {
                        "quote": "no",
                        "supports_fields": ["assertion"],
                        "chunk_hint": "s0:0",
                    }
                ],
            }
        },
        {
            "chunks": [
                {
                    "chunk_id": "s0",
                    "turns": [
                        {"speaker": "PACIENTE", "text": "no"},
                        {"speaker": "PACIENTE", "text": "no"},
                    ],
                }
            ]
        },
    )

    assert processed["allergy_summary"]["assertion"] is None


def test_summary_none_reported_valid_allergy_preserved() -> None:
    processed, _evidence, _stats = _process(
        {
            "allergy_summary": {
                "assertion": "none_reported",
                "scope_raw_text": "alergias",
                "evidence": [
                    {
                        "quote": "No tengo alergias",
                        "supports_fields": ["assertion", "scope_raw_text"],
                        "chunk_hint": "s0:0",
                    }
                ],
            }
        },
        {
            "chunks": [
                {
                    "chunk_id": "s0",
                    "turns": [{"speaker": "PACIENTE", "text": "No tengo alergias"}],
                }
            ]
        },
    )

    assert processed["allergy_summary"]["assertion"] == "none_reported"


def test_summary_penicillin_negation_not_global_allergy_none_reported() -> None:
    processed, _evidence, _stats = _process(
        {
            "allergy_summary": {
                "assertion": "none_reported",
                "scope_raw_text": None,
                "evidence": [
                    {
                        "quote": "No soy alérgico a la penicilina",
                        "supports_fields": ["assertion"],
                        "chunk_hint": "s0:0",
                    }
                ],
            },
            "allergies": [
                {
                    "substance_raw": "penicilina",
                    "reaction_raw": None,
                    "evidence": [
                        {
                            "quote": "No soy alérgico a la penicilina",
                            "supports_fields": ["substance_raw"],
                            "chunk_hint": "s0:0",
                        }
                    ],
                    **_common_claim_fields(),
                }
            ],
        },
        {
            "chunks": [
                {
                    "chunk_id": "s0",
                    "turns": [
                        {
                            "speaker": "PACIENTE",
                            "text": "No soy alérgico a la penicilina",
                        }
                    ],
                }
            ]
        },
    )

    assert processed["allergy_summary"]["assertion"] is None
    assert processed["allergies"][0]["substance_raw"] == "penicilina"


def test_summary_question_without_answer_stays_null() -> None:
    processed, _evidence, _stats = _process(
        {
            "allergy_summary": {
                "assertion": None,
                "scope_raw_text": None,
                "evidence": [],
            }
        },
        {
            "chunks": [
                {
                    "chunk_id": "s0",
                    "turns": [
                        {
                            "speaker": "MEDICO",
                            "text": "¿Tiene alguna alergia?",
                        }
                    ],
                }
            ]
        },
    )

    assert processed["allergy_summary"]["assertion"] is None


def test_summary_empty_array_without_domain_mention_stays_null() -> None:
    processed, _evidence, _stats = _process(
        {
            "allergies": [],
            "allergy_summary": {
                "assertion": None,
                "scope_raw_text": None,
                "evidence": [],
            }
        },
        {
            "chunks": [
                {
                    "chunk_id": "s0",
                    "turns": [
                        {"speaker": "PACIENTE", "text": "Me duele la cabeza"}
                    ],
                }
            ]
        },
    )

    assert processed["allergy_summary"]["assertion"] is None


def test_summary_degradation_does_not_remove_valid_allergy_facts() -> None:
    processed, _evidence, _stats = _process(
        {
            "allergy_summary": {
                "assertion": "none_reported",
                "scope_raw_text": None,
                "evidence": [],
            },
            "allergies": [
                {
                    "substance_raw": "penicilina",
                    "reaction_raw": "rash",
                    "evidence": [
                        {
                            "quote": "Soy alérgico a la penicilina y me da rash",
                            "supports_fields": ["substance_raw", "reaction_raw"],
                            "chunk_hint": "s0:0",
                        }
                    ],
                    **_common_claim_fields(),
                }
            ],
        },
        {
            "chunks": [
                {
                    "chunk_id": "s0",
                    "turns": [
                        {
                            "speaker": "PACIENTE",
                            "text": "Soy alérgico a la penicilina y me da rash",
                        }
                    ],
                }
            ]
        },
    )

    assert processed["allergy_summary"]["assertion"] is None
    assert processed["allergies"][0]["substance_raw"] == "penicilina"
    assert processed["allergies"][0]["reaction_raw"] == "rash"


def test_supports_fields_rejects_section_names_and_inferred_fields() -> None:
    processed, _evidence, stats = _process(
        {
            "medications": [
                {
                    "name_raw": "losartán",
                    "dose_value": None,
                    "dose_unit": None,
                    "route_raw": None,
                    "frequency_raw": None,
                    "timing_raw": None,
                    "exposure_duration_raw": None,
                    "prescribed_duration_raw": None,
                    "adherence_raw": None,
                    "medication_use_status": "current",
                    "certainty": "probable",
                    "prescribed_by": None,
                    "stopped_by": None,
                    "subject_role": "patient",
                    "subject_raw_text": None,
                    "information_source_role": "patient",
                    "evidence": [
                        {
                            "quote": "Toma losartán",
                            "supports_fields": [
                                "medications",
                                "name_raw",
                                "medication_use_status",
                            ],
                            "chunk_hint": "s0:0",
                        }
                    ],
                }
            ]
        },
        {
            "chunks": [
                {
                    "chunk_id": "s0",
                    "turns": [{"speaker": "PACIENTE", "text": "Toma losartán"}],
                }
            ]
        },
    )

    evidence = processed["medications"][0]["evidence"][0]
    assert evidence["supports_fields"] == ["name_raw"]
    assert stats["validation_warnings"] >= 1
    assert any(
        "invalid_section_reference:field=medications" in warning
        for warning in _warnings(processed)
    )
    assert any(
        "inferred_field_not_supported:field=medication_use_status" in warning
        for warning in _warnings(processed)
    )
