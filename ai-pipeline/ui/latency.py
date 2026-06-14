from __future__ import annotations

from datetime import datetime

STEP_LABELS = {
    "filtering": "Filtering",
    "clustering": "Clustering",
    "clustering_initial": "Clustering · inicial",
    "clustering_repair": "Clustering · repair",
    "classification": "Classification",
    "generation": "Generation",
    "context_pipeline": "Context pipeline",
}

E2E_BUCKET_ORDER = (
    "filtering",
    "clustering_initial",
    "clustering_repair",
    "clustering",
    "classification",
    "generation",
    "context_pipeline",
)


def _coerce_int_ms(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value))
    return None


def wall_time_ms_from_timestamps(payload: dict[str, object]) -> int | None:
    started = payload.get("run_started_at")
    finished = payload.get("run_finished_at")
    if not isinstance(started, str) or not isinstance(finished, str):
        return None
    try:
        started_at = datetime.fromisoformat(started)
        finished_at = datetime.fromisoformat(finished)
    except ValueError:
        return None
    delta_ms = int((finished_at - started_at).total_seconds() * 1000)
    return max(0, delta_ms)


def clustering_latency_ms(payload: dict[str, object]) -> tuple[int | None, int | None]:
    initial_ms = _coerce_int_ms(payload.get("initial_response_time_ms"))
    repair_ms = _coerce_int_ms(payload.get("repair_response_time_ms"))
    if initial_ms is not None:
        return initial_ms, repair_ms or 0
    return None, None


def clustering_has_split_latency(payload: dict[str, object]) -> bool:
    return _coerce_int_ms(payload.get("initial_response_time_ms")) is not None


def primary_latency_ms(step: str, payload: dict[str, object]) -> int | None:
    if step == "clustering":
        initial_ms, repair_ms = clustering_latency_ms(payload)
        if initial_ms is not None:
            return initial_ms + (repair_ms or 0)

    for key in ("total_response_time_ms", "response_time_ms"):
        resolved = _coerce_int_ms(payload.get(key))
        if resolved is not None:
            return resolved
    return wall_time_ms_from_timestamps(payload)


def secondary_latency_ms(step: str, payload: dict[str, object]) -> int | None:
    if step == "clustering":
        _, repair_ms = clustering_latency_ms(payload)
        if repair_ms is not None and repair_ms > 0:
            return repair_ms
        return None
    if step == "classification":
        return _coerce_int_ms(payload.get("sum_batch_response_time_ms"))
    if step == "generation":
        return _coerce_int_ms(payload.get("sum_section_response_time_ms"))
    return None


def latency_breakdown_rows(
    step: str,
    payload: dict[str, object],
) -> list[dict[str, object]]:
    if step == "clustering":
        repair_passes = payload.get("repair_passes")
        if not isinstance(repair_passes, list) or not repair_passes:
            return []
        rows: list[dict[str, object]] = []
        for repair_pass in repair_passes:
            if not isinstance(repair_pass, dict):
                continue
            rows.append(
                {
                    "pass": repair_pass.get("pass_index"),
                    "missing_turns": len(repair_pass.get("missing_turn_ids_before", []))
                    if isinstance(repair_pass.get("missing_turn_ids_before"), list)
                    else "",
                    "latencia_ms": repair_pass.get("response_time_ms"),
                }
            )
        return rows

    if step == "classification":
        batch_outputs = payload.get("batch_outputs")
        if not isinstance(batch_outputs, list):
            return []
        rows: list[dict[str, object]] = []
        for batch in batch_outputs:
            if not isinstance(batch, dict):
                continue
            cluster_ids = batch.get("cluster_ids")
            cluster_label = ""
            if isinstance(cluster_ids, list):
                cluster_label = ", ".join(str(cluster_id) for cluster_id in cluster_ids)
            rows.append(
                {
                    "batch": batch.get("batch_index"),
                    "clusters": cluster_label,
                    "latencia_ms": batch.get("response_time_ms"),
                }
            )
        return rows

    if step == "generation":
        section_outputs = payload.get("section_outputs")
        if not isinstance(section_outputs, list):
            return []
        rows = []
        for section in section_outputs:
            if not isinstance(section, dict):
                continue
            rows.append(
                {
                    "section_id": section.get("section_id"),
                    "latencia_ms": section.get("response_time_ms"),
                }
            )
        return rows

    return []


def _clustering_e2e_latency_rows(
    result_record: dict[str, object],
) -> list[dict[str, object]]:
    initial_ms, repair_ms = clustering_latency_ms(result_record)
    if initial_ms is not None:
        rows = [
            {
                "Paso": STEP_LABELS["clustering_initial"],
                "Latencia": format_latency_ms(initial_ms),
                "latencia_ms": initial_ms,
            }
        ]
        if repair_ms is not None and repair_ms > 0:
            rows.append(
                {
                    "Paso": STEP_LABELS["clustering_repair"],
                    "Latencia": format_latency_ms(repair_ms),
                    "latencia_ms": repair_ms,
                }
            )
        return rows

    latency_ms = primary_latency_ms("clustering", result_record)
    return [
        {
            "Paso": STEP_LABELS["clustering"],
            "Latencia": format_latency_ms(latency_ms),
            "latencia_ms": latency_ms,
        }
    ]


def format_latency_ms(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value:,} ms"


def e2e_latency_rows(
    outputs: list[dict[str, object]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    total_ms = 0
    has_any = False

    for entry in outputs:
        if not isinstance(entry, dict):
            continue
        step = entry.get("step")
        result_record = entry.get("result_record")
        if not isinstance(step, str) or not isinstance(result_record, dict):
            continue

        if step == "clustering":
            step_rows = _clustering_e2e_latency_rows(result_record)
            for step_row in step_rows:
                latency_ms = step_row.get("latencia_ms")
                if isinstance(latency_ms, int):
                    total_ms += latency_ms
                    has_any = True
            rows.extend(step_rows)
            continue

        latency_ms = primary_latency_ms(step, result_record)
        if latency_ms is not None:
            total_ms += latency_ms
            has_any = True
        rows.append(
            {
                "Paso": STEP_LABELS.get(step, step),
                "Latencia": format_latency_ms(latency_ms),
                "latencia_ms": latency_ms,
            }
        )

    if has_any:
        rows.append(
            {
                "Paso": "Total (secuencial)",
                "Latencia": format_latency_ms(total_ms),
                "latencia_ms": total_ms,
            }
        )

    display_rows = [
        {"Paso": row["Paso"], "Latencia": row["Latencia"]}
        for row in rows
    ]
    return display_rows


__all__ = [
    "E2E_BUCKET_ORDER",
    "STEP_LABELS",
    "clustering_has_split_latency",
    "clustering_latency_ms",
    "e2e_latency_rows",
    "format_latency_ms",
    "latency_breakdown_rows",
    "primary_latency_ms",
    "secondary_latency_ms",
    "wall_time_ms_from_timestamps",
]
