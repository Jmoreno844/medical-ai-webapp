from __future__ import annotations

from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.encounters.api import _delete_encounter_dependents


class RecordingSession:
    def __init__(self) -> None:
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> None:
        self.statements.append(statement)


@pytest.mark.asyncio
async def test_delete_encounter_dependents_clears_child_rows_before_documents() -> None:
    session = RecordingSession()

    await _delete_encounter_dependents(
        cast(AsyncSession, session),
        encounter_id=4,
        doctor_id=7,
    )

    deleted_table_names = [statement.table.name for statement in session.statements]
    assert deleted_table_names == [
        "transcription_audio_section",
        "transcription_recording_session",
        "copilot_copilotpatch",
        "copilot_copilotpatchset",
        "copilot_copilotrun",
        "documents_document",
    ]
