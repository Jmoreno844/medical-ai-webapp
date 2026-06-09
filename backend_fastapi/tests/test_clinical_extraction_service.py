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


def test_build_extraction_chunks_uses_deterministic_turn_ids() -> None:
    chunks = _build_extraction_chunks(
        {
            "chunks": [
                {
                    "chunk_id": "section-a",
                    "start_ms": 100,
                    "end_ms": 500,
                    "turns": [
                        {"speaker": "PACIENTE", "text": "Me duele la cabeza."},
                        {"speaker": "MEDICO", "text": "Desde cuando?"},
                    ],
                }
            ]
        }
    )

    assert [chunk.chunk_id for chunk in chunks] == ["section-a:0", "section-a:1"]
    assert chunks[0].speaker == "patient"
    assert chunks[1].speaker == "clinician"


def test_process_clinical_facts_links_evidence_and_injects_metadata() -> None:
    chunks = _build_extraction_chunks(
        {
            "chunks": [
                {
                    "chunk_id": "s0",
                    "turns": [
                        {"speaker": "PACIENTE", "text": "Me duele la cabeza fuerte."}
                    ],
                }
            ]
        }
    )
    facts = {
        "clinical_events": [
            {
                "concept_raw_text": "dolor de cabeza",
                "severity_raw": "fuerte",
                "information_source_role": "patient",
                "evidence": [
                    {
                        "quote": "Me duele la cabeza fuerte",
                        "supports_fields": ["concept_raw_text", "severity_raw"],
                        "chunk_hint": "s0:0",
                    }
                ],
            }
        ]
    }

    processed, evidence, stats = process_clinical_facts(
        facts,
        chunks,
        recording_session=_recording_session(),  # type: ignore[arg-type]
    )

    assert evidence[0].matched is True
    assert evidence[0].uttered_by_role == "patient"
    assert stats["fields_grounded"] >= 2
    assert stats["fields_flagged_ungrounded"] == 0
    assert processed["record_metadata"]["schema_version"] == "clinical_facts_v1"
    assert processed["patient"]["id"] == 40


def test_process_clinical_facts_does_not_mark_exact_turn_quote_ambiguous() -> None:
    chunks = _build_extraction_chunks(
        {
            "chunks": [
                {
                    "chunk_id": "section-a",
                    "turns": [
                        {"speaker": "MEDICO", "text": "Cuénteme qué pasó."},
                        {
                            "speaker": "PACIENTE",
                            "text": "Me duele la cabeza fuerte desde ayer.",
                        },
                    ],
                }
            ]
        }
    )
    facts = {
        "clinical_events": [
            {
                "concept_raw_text": "cabeza",
                "severity_raw": "fuerte",
                "onset_raw": "desde ayer",
                "information_source_role": "patient",
                "assertion": "present",
                "claim_lifecycle": "active",
                "subject_role": "patient",
                "evidence": [
                    {
                        "quote": "Me duele la cabeza fuerte desde ayer.",
                        "supports_fields": [
                            "concept_raw_text",
                            "severity_raw",
                            "onset_raw",
                        ],
                        "chunk_hint": "section-a:1",
                    }
                ],
            }
        ]
    }

    processed, evidence, stats = process_clinical_facts(
        facts,
        chunks,
        recording_session=_recording_session(),  # type: ignore[arg-type]
    )

    assert evidence[0].matched is True
    assert evidence[0].ambiguous is False
    assert evidence[0].matched_chunk_ids == ["section-a:1"]
    assert evidence[0].uttered_by_role == "patient"
    assert stats["quotes_ambiguous"] == 0
    assert not any(
        "quote_ambiguous"
        in warning
        for warning in processed["data_quality"]["extraction_warnings"]
    )


def test_process_clinical_facts_flags_ambiguous_short_quote() -> None:
    chunks = _build_extraction_chunks(
        {
            "chunks": [
                {"chunk_id": "s0", "turns": [{"speaker": "PACIENTE", "text": "Si"}]},
                {"chunk_id": "s1", "turns": [{"speaker": "PACIENTE", "text": "Si"}]},
            ]
        }
    )
    facts = {
        "clinical_events": [
            {
                "concept_raw_text": "respuesta afirmativa",
                "information_source_role": "patient",
                "evidence": [
                    {
                        "quote": "Si",
                        "supports_fields": ["concept_raw_text"],
                        "chunk_hint": None,
                    }
                ],
            }
        ]
    }

    processed, evidence, stats = process_clinical_facts(
        facts,
        chunks,
        recording_session=_recording_session(),  # type: ignore[arg-type]
    )

    assert evidence[0].ambiguous is True
    assert stats["quotes_ambiguous"] == 1
    assert "quote_ambiguous" in processed["data_quality"]["extraction_warnings"][0]


def test_process_clinical_facts_forces_ground_strict_null() -> None:
    chunks = _build_extraction_chunks(
        {
            "chunks": [
                {
                    "chunk_id": "s0",
                    "turns": [
                        {
                            "speaker": "PACIENTE",
                            "text": "Tomo losartan todas las mañanas.",
                        }
                    ],
                }
            ]
        }
    )
    facts = {
        "medications": [
            {
                "name_raw": "losartan",
                "dose_value": "50",
                "information_source_role": "patient",
                "evidence": [
                    {
                        "quote": "Tomo losartan todas las mañanas",
                        "supports_fields": ["name_raw", "dose_value"],
                        "chunk_hint": "s0:0",
                    }
                ],
            }
        ]
    }

    processed, _evidence, stats = process_clinical_facts(
        facts,
        chunks,
        recording_session=_recording_session(),  # type: ignore[arg-type]
    )

    assert processed["medications"][0]["dose_value"] is None
    assert stats["ground_strict_forced_null"] == 1


def test_process_clinical_facts_warns_unsupported_allergy_summary() -> None:
    chunks = _build_extraction_chunks(
        {
            "language": "es",
            "chunks": [
                {
                    "chunk_id": "s0",
                    "turns": [
                        {
                            "speaker": "PACIENTE",
                            "text": "Me duele la cabeza fuerte desde ayer.",
                        }
                    ],
                }
            ],
        }
    )
    facts = {
        "allergy_summary": {
            "assertion": "none_reported",
            "scope_raw_text": None,
            "evidence": [
                {
                    "quote": "Me duele la cabeza fuerte desde ayer.",
                    "supports_fields": ["assertion"],
                    "chunk_hint": "s0:0",
                }
            ],
        }
    }

    processed, evidence, stats = process_clinical_facts(
        facts,
        chunks,
        recording_session=_recording_session(),  # type: ignore[arg-type]
    )

    assert evidence[0].matched is True
    assert processed["allergy_summary"]["assertion"] is None
    assert processed["allergy_summary"]["evidence"] == []
    assert stats["validation_warnings"] >= 1
    assert any(
        "collection_summary_none_reported_without_explicit_evidence" in warning
        for warning in processed["data_quality"]["extraction_warnings"]
    )


def test_process_clinical_facts_warns_invalid_medication_decision_status() -> None:
    chunks = _build_extraction_chunks(
        {
            "chunks": [
                {
                    "chunk_id": "s0",
                    "turns": [
                        {
                            "speaker": "PACIENTE",
                            "text": "Tomo losartan todas las mañanas.",
                        }
                    ],
                }
            ]
        }
    )
    facts = {
        "medications": [
            {
                "name_raw": "losartan",
                "decision_status": "present",
                "information_source_role": "patient",
                "assertion": "present",
                "claim_lifecycle": "active",
                "evidence": [
                    {
                        "quote": "Tomo losartan todas las mañanas.",
                        "supports_fields": ["name_raw"],
                        "chunk_hint": "s0:0",
                    }
                ],
            }
        ]
    }

    processed, _evidence, stats = process_clinical_facts(
        facts,
        chunks,
        recording_session=_recording_session(),  # type: ignore[arg-type]
    )

    medication = processed["medications"][0]
    assert medication.get("decision_status") is None
    assert medication.get("assertion") is None
    assert medication.get("claim_lifecycle") is None
    assert stats["validation_warnings"] >= 1
    warnings = processed["data_quality"]["extraction_warnings"]
    assert any(
        "medications[0].decision_status: field_not_allowed" in warning
        for warning in warnings
    )


def test_process_clinical_facts_warns_duplicate_proposition_between_sections() -> None:
    chunks = _build_extraction_chunks(
        {
            "chunks": [
                {
                    "chunk_id": "s0",
                    "turns": [
                        {
                            "speaker": "PACIENTE",
                            "text": "Me duele la cabeza fuerte desde ayer.",
                        }
                    ],
                }
            ]
        }
    )
    duplicate_fact = {
        "concept_raw_text": "dolor de cabeza",
        "evidence": [
            {
                "quote": "Me duele la cabeza fuerte desde ayer.",
                "supports_fields": ["concept_raw_text"],
                "chunk_hint": "s0:0",
            }
        ],
    }
    facts = {
        "chief_complaints": [duplicate_fact],
        "clinical_events": [duplicate_fact.copy()],
    }

    processed, _evidence, stats = process_clinical_facts(
        facts,
        chunks,
        recording_session=_recording_session(),  # type: ignore[arg-type]
    )

    assert stats["validation_warnings"] == 1
    assert (
        "clinical_events[0]: duplicate_proposition_removed:chief_complaints[0]"
        in processed["data_quality"]["extraction_warnings"]
    )


def test_process_clinical_facts_injects_language_from_transcript() -> None:
    processed, _evidence, _stats = process_clinical_facts(
        {"clinical_events": []},
        [],
        recording_session=_recording_session(),  # type: ignore[arg-type]
        language="es",
    )

    assert processed["record_metadata"]["language"] == "es"
