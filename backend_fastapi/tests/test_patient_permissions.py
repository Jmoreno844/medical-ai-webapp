from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.encounters import api as encounters_api
from app.domains.encounters.schemas import EncounterUpdate
from app.domains.patients import api as patients_api


class FakeScalarResult:
    def __init__(self, value: Any) -> None:
        self.value = value

    def scalar_one_or_none(self) -> Any:
        return self.value

    def scalar_one(self) -> Any:
        return self.value

    def scalars(self) -> "FakeScalarResult":
        return self

    def all(self) -> list[Any]:
        return list(self.value)


class RecordingSession:
    def __init__(self, results: list[FakeScalarResult] | None = None) -> None:
        self.results = results or []
        self.statements: list[Any] = []
        self.committed = False

    async def execute(self, statement: Any) -> FakeScalarResult:
        self.statements.append(statement)
        if getattr(statement, "is_select", False) and self.results:
            return self.results.pop(0)
        return FakeScalarResult(None)

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, _value: Any) -> None:
        return None


@pytest.mark.asyncio
async def test_update_encounter_rejects_patient_from_another_doctor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_encounter_or_404(*args, **kwargs):
        return SimpleNamespace(id=10, doctor_id=7, encounter_name="Actual")

    monkeypatch.setattr(
        encounters_api,
        "_get_encounter_or_404",
        fake_get_encounter_or_404,
    )

    session = RecordingSession(results=[FakeScalarResult(None)])
    user = SimpleNamespace(id=7)

    with pytest.raises(HTTPException) as exc_info:
        await encounters_api.update_encounter(
            10,
            EncounterUpdate(patient_id=99, patient_connected=True),
            user=cast(Any, user),
            session=cast(AsyncSession, session),
        )

    assert exc_info.value.status_code == 404
    assert session.committed is False


@pytest.mark.asyncio
async def test_delete_patient_for_doctor_removes_owned_encounters_and_patient_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_patient_for_doctor(*args, **kwargs):
        return SimpleNamespace(id=5, name="Ana")

    monkeypatch.setattr(
        patients_api,
        "_get_patient_for_doctor",
        fake_get_patient_for_doctor,
    )

    session = RecordingSession(
        results=[
            FakeScalarResult([11, 12]),
            FakeScalarResult(0),
        ]
    )

    await patients_api.delete_patient_for_doctor(
        cast(AsyncSession, session),
        patient_id=5,
        doctor_id=7,
    )

    deleted_table_names = [
        statement.table.name
        for statement in session.statements
        if hasattr(statement, "table")
    ]
    assert deleted_table_names == [
        "transcription_audio_section",
        "transcription_recording_session",
        "copilot_copilotpatch",
        "copilot_copilotpatchset",
        "copilot_copilotrun",
        "documents_document",
        "transcription_audio_section",
        "transcription_recording_session",
        "copilot_copilotpatch",
        "copilot_copilotpatchset",
        "copilot_copilotrun",
        "documents_document",
        "encounters_encounter",
        "patients_patientdoctor",
        "patients_patient",
    ]


@pytest.mark.asyncio
async def test_delete_patient_for_doctor_keeps_shared_patient_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_patient_for_doctor(*args, **kwargs):
        return SimpleNamespace(id=5, name="Ana")

    monkeypatch.setattr(
        patients_api,
        "_get_patient_for_doctor",
        fake_get_patient_for_doctor,
    )

    session = RecordingSession(
        results=[
            FakeScalarResult([]),
            FakeScalarResult(1),
        ]
    )

    await patients_api.delete_patient_for_doctor(
        cast(AsyncSession, session),
        patient_id=5,
        doctor_id=7,
    )

    deleted_table_names = [
        statement.table.name
        for statement in session.statements
        if hasattr(statement, "table")
    ]
    assert deleted_table_names == ["patients_patientdoctor"]
