from __future__ import annotations

from ui.triage_audit import (
    DISPOSITION_CONTENT,
    DISPOSITION_DROPPED,
    DISPOSITION_UNCLASSIFIED,
    triage_item_disposition_rows,
)


def test_triage_item_disposition_marks_dropped_meta_instruction() -> None:
    rows = triage_item_disposition_rows(
        [
            {"id": "1", "text": "No tomes casi nada de la epicrisis."},
            {"id": "2", "text": "Paciente alérgico a penicilina."},
        ],
        content_ids=[],
        drop_ids=["1"],
    )
    assert rows[0]["disposición"] == DISPOSITION_DROPPED
    assert rows[1]["disposición"] == DISPOSITION_UNCLASSIFIED


def test_triage_item_disposition_marks_clinical_content() -> None:
    rows = triage_item_disposition_rows(
        [{"id": "2", "text": "Paciente alérgico a penicilina."}],
        content_ids=[2],
        drop_ids=[],
    )
    assert rows[0]["disposición"] == DISPOSITION_CONTENT


def test_triage_item_disposition_normalizes_integer_ids() -> None:
    rows = triage_item_disposition_rows(
        [{"id": "1", "text": "meta"}],
        content_ids=[],
        drop_ids=[1],
    )
    assert rows[0]["disposición"] == DISPOSITION_DROPPED
