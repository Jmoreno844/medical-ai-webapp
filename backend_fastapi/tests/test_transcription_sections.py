from __future__ import annotations

from app.domains.transcription.service import _merge_with_light_dedup


def test_merge_with_light_dedup_removes_boundary_overlap() -> None:
    merged = _merge_with_light_dedup(
        "El paciente refiere dolor abdominal desde ayer.",
        "desde ayer. Niega fiebre.",
    )

    assert merged == "El paciente refiere dolor abdominal desde ayer. Niega fiebre."
