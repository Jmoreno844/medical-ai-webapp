from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.domains.clinical_extraction.debug_controller import (
    run_debug_clinical_extraction,
)
from app.domains.clinical_extraction.schemas import DebugClinicalExtractionRequest


@pytest.mark.asyncio
async def test_run_debug_clinical_extraction_is_reusable_outside_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_worker_call(*, settings, work_item, provider, model) -> dict:
        assert work_item["language"] == "es"
        assert work_item["session_id"] == "eval-case-1"
        return {
            "success": True,
            "facts": {
                "mentions": [
                    {
                        "entity_type": "medication",
                        "entity_raw": "ibuprofeno",
                        "proposition_raw": "No tome ibuprofeno",
                        "speech_act": "instruction_to_avoid",
                        "subject_role": "patient",
                        "attributes": [],
                        "evidence": [
                            {
                                "quote": "No tome ibuprofeno",
                                "turn_id": "s0:1",
                            }
                        ],
                    }
                ]
            },
            "extraction_model": "gpt-5.4-mini",
            "latency_ms": 250,
            "provider": "openai",
        }

    payload = DebugClinicalExtractionRequest(
        transcript_json={
            "session_id": "eval-case-1",
            "language": "es",
            "chunks": [
                {
                    "chunk_id": "s0",
                    "turns": [
                        {"speaker": "MEDICO", "text": "No tome ibuprofeno."},
                    ],
                }
            ],
        }
    )

    response = await run_debug_clinical_extraction(
        payload=payload,
        db_session=SimpleNamespace(),
        settings=SimpleNamespace(clinical_extraction_worker_base_url="http://localhost:8093"),
        worker_caller=fake_worker_call,
    )

    assert response.status == "extracted"
    assert response.session_id == "eval-case-1"
    assert response.processed_mentions["mentions"][0]["speech_act"] == "instruction_to_avoid"
    assert response.evidence[0].matched is True
