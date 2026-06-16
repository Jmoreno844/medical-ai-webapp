from __future__ import annotations

from harness.context_cases import DoctorNoteCase

from ui.context_runner import _load_context_case_bundle


def test_load_context_case_bundle_uses_repo_case_by_default() -> None:
    case_meta, bundle, _cases_index = _load_context_case_bundle(
        context_case_id="case1",
    )
    assert case_meta.id == "case1"
    assert bundle.doctor_note.session_id == "case1"


def test_load_context_case_bundle_accepts_pasted_doctor_note() -> None:
    doctor_note_case = DoctorNoteCase(
        session_id="adhoc",
        doctor_note="Paciente alérgico a penicilina.",
    )
    case_meta, bundle, _cases_index = _load_context_case_bundle(
        context_case_id=None,
        doctor_note_case=doctor_note_case,
        encounter_date="2026-06-14",
    )
    assert case_meta.id == "pasted_adhoc"
    assert case_meta.encounter_date == "2026-06-14"
    assert bundle is doctor_note_case
