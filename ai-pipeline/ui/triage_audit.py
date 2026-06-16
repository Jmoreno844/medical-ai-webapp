from __future__ import annotations

DISPOSITION_CONTENT = "Contenido clínico"
DISPOSITION_DROPPED = "Descartado (meta-instrucción o ruido)"
DISPOSITION_DROPPED_AND_CONTENT = "Contenido clínico y descartado (revisar)"
DISPOSITION_UNCLASSIFIED = "Sin clasificar por el modelo"


def _normalize_id_set(raw_ids: object) -> set[str]:
    if not isinstance(raw_ids, list):
        return set()
    return {str(item_id) for item_id in raw_ids if item_id is not None and str(item_id)}


def triage_item_disposition_rows(
    doctor_items: object,
    *,
    content_ids: object,
    drop_ids: object,
) -> list[dict[str, str]]:
    if not isinstance(doctor_items, list):
        return []

    content_set = _normalize_id_set(content_ids)
    drop_set = _normalize_id_set(drop_ids)
    rows: list[dict[str, str]] = []

    for item in doctor_items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id", ""))
        text = str(item.get("text", ""))
        in_content = item_id in content_set
        in_drop = item_id in drop_set

        if in_content and in_drop:
            disposition = DISPOSITION_DROPPED_AND_CONTENT
        elif in_content:
            disposition = DISPOSITION_CONTENT
        elif in_drop:
            disposition = DISPOSITION_DROPPED
        else:
            disposition = DISPOSITION_UNCLASSIFIED

        rows.append(
            {
                "id": item_id,
                "disposición": disposition,
                "texto": text,
            }
        )

    return rows


__all__ = [
    "DISPOSITION_CONTENT",
    "DISPOSITION_DROPPED",
    "DISPOSITION_DROPPED_AND_CONTENT",
    "DISPOSITION_UNCLASSIFIED",
    "triage_item_disposition_rows",
]
