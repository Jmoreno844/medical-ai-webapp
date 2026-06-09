from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.domains.clinical_extraction.service import (
    _build_extraction_chunks,
    process_clinical_facts,
)

CASES_PATH = (
    Path(__file__).resolve().parents[2]
    / "evals"
    / "document_generation"
    / "cases.json"
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


def _eval_case_001_transcript() -> dict:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    case = next(item for item in cases if item["id"] == "eval_case_001")
    sections = case["transcription"]["sections"]
    return {
        "language": case["transcription"]["language"],
        "chunks": [
            {
                "chunk_id": f"section-{section['section_index']}",
                "turns": [
                    {
                        "speaker": turn["speaker"].upper(),
                        "text": turn["text"],
                    }
                    for turn in section["turns"]
                ],
            }
            for section in sections
        ],
    }


def _eval_case_001_facts() -> dict:
    evidence = lambda quote, fields: {
        "quote": quote,
        "supports_fields": fields,
        "chunk_hint": None,
    }
    return {
        "information_sources": [],
        "chief_complaints": [
            {
                "text_raw": "ardor para orinar y dolor bajito",
                "information_source_role": "patient",
                "evidence": [
                    evidence(
                        "llevo como tres dias con un ardor para orinar terrible y un dolor bajito",
                        ["text_raw"],
                    )
                ],
            }
        ],
        "clinical_events": [
            {
                "event_kind": "symptom",
                "concept_raw_text": "hematuria con coagulos",
                "value_raw": None,
                "body_site_raw": None,
                "laterality_raw": None,
                "severity_raw": None,
                "onset_raw": "ayer por la tarde",
                "duration_raw": None,
                "time_expression_raw": None,
                "assertion": "present",
                "claim_lifecycle": "active",
                "reported_certainty": "stated_plainly",
                "subject_role": "patient",
                "subject_raw_text": None,
                "information_source_role": "patient",
                "evidence": [
                    evidence(
                        "orine como rojito, como con sangre y unos coagulos chiquitos",
                        ["concept_raw_text", "onset_raw"],
                    )
                ],
            }
        ],
        "history": {
            "conditions": [],
            "surgeries_and_procedures": [],
            "trauma": [],
            "family_history": [],
            "gynecologic_obstetric": [],
            "social_history": [
                {
                    "concept_raw_text": "losartan de esposo ocasional",
                    "subject_role": "patient",
                    "subject_raw_text": None,
                    "information_source_role": "patient",
                    "assertion": "present",
                    "claim_lifecycle": "active",
                    "reported_certainty": "hedged",
                    "evidence": [
                        evidence(
                            "a veces me tomo un losartan de mi esposo cuando me duele mucho la cabeza",
                            ["concept_raw_text"],
                        )
                    ],
                }
            ],
            "exposures": [],
            "unclassified_explicit_history_facts": [],
        },
        "allergies": [
            {
                "substance_raw": "penicilina",
                "reaction_raw": "enroncho",
                "severity_raw": None,
                "certainty": "possible",
                "allergy_clinical_status": "inactive",
                "claim_lifecycle": "superseded",
                "subject_role": "patient",
                "subject_raw_text": None,
                "information_source_role": "patient",
                "evidence": [
                    evidence(
                        "a la penicilina me enroncho toda",
                        ["substance_raw", "reaction_raw"],
                    )
                ],
            },
            {
                "substance_raw": "sulfas",
                "reaction_raw": "brote en la piel",
                "severity_raw": None,
                "certainty": "confirmed",
                "allergy_clinical_status": "active",
                "claim_lifecycle": "active",
                "subject_role": "patient",
                "subject_raw_text": None,
                "information_source_role": "patient",
                "evidence": [
                    evidence(
                        "Es a la sulfa, a las sulfas que me dieron para otra infeccion urinaria",
                        ["substance_raw", "reaction_raw"],
                    )
                ],
            },
        ],
        "allergy_summary": {
            "assertion": None,
            "scope_raw_text": None,
            "evidence": [],
        },
        "medications": [
            {
                "name_raw": "nitrofurantoína",
                "dose_value": "100",
                "dose_unit": "mg",
                "route_raw": None,
                "frequency_raw": "cada doce horas",
                "timing_raw": None,
                "exposure_duration_raw": "cinco dias",
                "prescribed_duration_raw": "cinco dias",
                "adherence_raw": None,
                "medication_use_status": "prescribed",
                "certainty": "confirmed",
                "prescribed_by": "clinician",
                "stopped_by": None,
                "subject_role": "patient",
                "subject_raw_text": None,
                "information_source_role": "clinician",
                "evidence": [
                    evidence(
                        "nitrofurantoina de cien miligramos, una cada doce horas por cinco dias",
                        ["name_raw", "dose_value", "frequency_raw"],
                    )
                ],
            }
        ],
        "medication_summary": {
            "assertion": None,
            "scope_raw_text": None,
            "evidence": [],
        },
        "objective_data": {
            "vital_signs": [],
            "anthropometrics": [],
            "physical_exam_findings": [],
        },
        "diagnostic_studies": [
            {
                "name_raw": "parcial de orina",
                "category": "laboratorio",
                "lifecycle_stage": "specimen_collected",
                "result_availability": "pending",
                "result_content_raw": None,
                "subject_role": "patient",
                "subject_raw_text": None,
                "information_source_role": "clinician",
                "evidence": [
                    evidence(
                        "Le voy a mandar parcial de orina y urocultivo",
                        ["name_raw", "lifecycle_stage"],
                    )
                ],
            },
            {
                "name_raw": "urocultivo",
                "category": "laboratorio",
                "lifecycle_stage": "specimen_collected",
                "result_availability": "pending",
                "result_content_raw": None,
                "subject_role": "patient",
                "subject_raw_text": None,
                "information_source_role": "clinician",
                "evidence": [
                    evidence(
                        "se los tomo esta manana en el laboratorio no tenemos los resultados todavia",
                        ["name_raw", "result_availability", "result_content_raw"],
                    )
                ],
            },
        ],
        "interventions": [],
        "clinician_assessment": {
            "stated_impressions": [],
            "stated_diagnoses": [],
            "stated_differentials": [],
            "stated_risk_assessments": [],
        },
        "care_plan": {
            "recommendations": [
                {
                    "text_raw": "no tomar ibuprofeno ni diclofenaco ni otros AINES",
                    "conditional_on_raw_text": None,
                    "evidence": [
                        evidence(
                            "No, por favor no tome ibuprofeno ni diclofenaco ni otros AINES",
                            ["text_raw"],
                        )
                    ],
                },
                {
                    "text_raw": "tomar acetaminofen quinientos miligramos si duele mucho",
                    "conditional_on_raw_text": None,
                    "evidence": [
                        evidence(
                            "Tomese mas bien acetaminofen si le duele mucho, quinientos miligramos",
                            ["text_raw"],
                        )
                    ],
                },
            ],
            "education": [],
            "warning_signs": [
                {
                    "text_raw": "ir a urgencias si fiebre muy alta o dolor insoportable en la espalda",
                    "conditional_on_raw_text": "fiebre muy alta o dolor insoportable en la espalda",
                    "evidence": [
                        evidence(
                            "Si llega a tener fiebre muy alta o el dolor se vuelve insoportable en la espalda, se va de una vez por urgencias",
                            ["text_raw", "conditional_on_raw_text"],
                        )
                    ],
                }
            ],
            "disposition": {
                "text_raw": None,
                "conditional_on_raw_text": None,
                "evidence": [],
            },
            "work_leave": {
                "text_raw": None,
                "conditional_on_raw_text": None,
                "evidence": [],
            },
            "follow_up": {
                "text_raw": "control con resultado del examen",
                "conditional_on_raw_text": None,
                "evidence": [
                    evidence(
                        "Nos vemos con el resultado del examen",
                        ["text_raw"],
                    )
                ],
            },
        },
        "data_quality": {
            "corrections": [
                {
                    "fact_path_raw": "allergies[0].substance_raw",
                    "prior_value_raw": "penicilina",
                    "replacement_value_raw": "sulfas",
                    "repair_language_raw": "no es a la penicilina, es a la sulfa",
                    "prior_evidence": [
                        evidence(
                            "a la penicilina me enroncho toda",
                            ["prior_value_raw"],
                        )
                    ],
                    "replacement_evidence": [
                        evidence(
                            "Es a la sulfa, a las sulfas",
                            ["replacement_value_raw"],
                        )
                    ],
                    "repair_evidence": [
                        evidence(
                            "no, no es a la penicilina",
                            ["repair_language_raw"],
                        )
                    ],
                }
            ],
            "unresolved_conflicts": [],
        },
        "custom_facts": [],
    }


def test_eval_case_001_regression_post_process() -> None:
    transcript = _eval_case_001_transcript()
    chunks = _build_extraction_chunks(transcript)
    processed, _evidence, _stats = process_clinical_facts(
        _eval_case_001_facts(),
        chunks,
        recording_session=_recording_session(),  # type: ignore[arg-type]
        language=transcript.get("language"),
    )

    medication_names = [
        str(item.get("name_raw") or "").lower()
        for item in processed.get("medications", [])
        if isinstance(item, dict) and item.get("name_raw")
    ]
    assert not any("ibuprof" in name for name in medication_names)
    assert any("nitrofur" in name for name in medication_names)
    assert len(medication_names) == 1

    studies = [
        item
        for item in processed.get("diagnostic_studies", [])
        if isinstance(item, dict) and item.get("name_raw")
    ]
    study_names = {str(item["name_raw"]).lower() for item in studies}
    assert "parcial de orina" in study_names
    assert "urocultivo" in study_names
    assert all(item.get("result_availability") == "pending" for item in studies)
    assert all(item.get("result_content_raw") is None for item in studies)

    care_plan = processed.get("care_plan", {})
    care_plan_text = json.dumps(care_plan, ensure_ascii=False).lower()
    assert "ibuprofeno" in care_plan_text or "aines" in care_plan_text
    assert "nitrofur" not in care_plan_text
    assert "urocultivo" not in care_plan_text
    assert "parcial de orina" not in care_plan_text

    event_text = json.dumps(
        processed.get("clinical_events", []),
        ensure_ascii=False,
    ).lower()
    assert "nitrofur" not in event_text
    assert "urocultivo" not in event_text
    assert "ibuprofeno" not in event_text

    allergies = processed.get("allergies", [])
    penicillin = next(
        item
        for item in allergies
        if isinstance(item, dict)
        and str(item.get("substance_raw", "")).lower().startswith("penicil")
    )
    sulfa = next(
        item
        for item in allergies
        if isinstance(item, dict) and "sulfa" in str(item.get("substance_raw", "")).lower()
    )
    assert penicillin.get("claim_lifecycle") == "superseded"
    assert sulfa.get("claim_lifecycle") == "active"

    corrections = processed.get("data_quality", {}).get("corrections", [])
    assert len(corrections) == 1
    correction = corrections[0]
    assert correction.get("prior_evidence")
    assert correction.get("replacement_evidence")
    assert correction.get("repair_evidence")

    objective = processed.get("objective_data", {})
    assert objective.get("vital_signs") == []
    assert objective.get("anthropometrics") == []
    assert objective.get("physical_exam_findings") == []
