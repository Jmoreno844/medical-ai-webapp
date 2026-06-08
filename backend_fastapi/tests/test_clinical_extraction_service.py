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
    assert processed["record_metadata"]["schema_version"] == "clinical_facts_v1"
    assert processed["patient"]["id"] == 40


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
