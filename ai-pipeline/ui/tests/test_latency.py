from __future__ import annotations

from ui.latency import (
    e2e_latency_rows,
    primary_latency_ms,
    secondary_latency_ms,
    wall_time_ms_from_timestamps,
)


def test_wall_time_ms_from_timestamps() -> None:
    payload = {
        "run_started_at": "2026-06-12T22:23:21.487337+00:00",
        "run_finished_at": "2026-06-12T22:23:24.675182+00:00",
    }
    assert wall_time_ms_from_timestamps(payload) == 3187


def test_primary_latency_prefers_total_response_time_ms() -> None:
    payload = {
        "total_response_time_ms": 3100,
        "run_started_at": "2026-06-12T22:23:21+00:00",
        "run_finished_at": "2026-06-12T22:23:24+00:00",
    }
    assert primary_latency_ms("classification", payload) == 3100


def test_primary_latency_falls_back_to_response_time_ms() -> None:
    payload = {"response_time_ms": 1523}
    assert primary_latency_ms("filtering", payload) == 1523


def test_primary_latency_falls_back_to_timestamps() -> None:
    payload = {
        "run_started_at": "2026-06-12T22:23:21+00:00",
        "run_finished_at": "2026-06-12T22:23:23+00:00",
    }
    assert primary_latency_ms("clustering", payload) == 2000


def test_secondary_latency_for_classification_and_generation() -> None:
    assert secondary_latency_ms("classification", {"sum_batch_response_time_ms": 4215}) == 4215
    assert secondary_latency_ms("generation", {"sum_section_response_time_ms": 11885}) == 11885
    assert secondary_latency_ms("filtering", {"response_time_ms": 100}) is None


def test_e2e_latency_rows_sums_step_latencies() -> None:
    outputs = [
        {
            "step": "filtering",
            "result_record": {"response_time_ms": 1000},
        },
        {
            "step": "clustering",
            "result_record": {"response_time_ms": 2000},
        },
        {
            "step": "classification",
            "result_record": {"total_response_time_ms": 3000},
        },
        {
            "step": "generation",
            "result_record": {"total_response_time_ms": 4000},
        },
    ]
    rows = e2e_latency_rows(outputs)
    assert rows[-1]["Paso"] == "Total (secuencial)"
    assert rows[-1]["Latencia"] == "10,000 ms"
