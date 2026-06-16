from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class TranscriptCase:
    id: str
    transcript_json: dict[str, object]
    notes: str | None = None


def load_cases(index_path: Path) -> list[TranscriptCase]:
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("ai_pipeline_cases_index_must_be_a_list")

    cases_root = index_path.parent
    cases: list[TranscriptCase] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"ai_pipeline_case_{index}_must_be_an_object")
        case_id = item.get("id")
        notes = item.get("notes")
        transcript_json = item.get("transcript_json")
        transcript_file = item.get("transcript_file")

        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"ai_pipeline_case_{index}_id_must_be_non_empty")
        if notes is not None and not isinstance(notes, str):
            raise ValueError(f"ai_pipeline_case_{index}_notes_must_be_str")

        if transcript_json is not None and transcript_file is not None:
            raise ValueError(
                f"ai_pipeline_case_{index}_must_use_transcript_json_or_file"
            )
        if transcript_json is None and transcript_file is None:
            raise ValueError(f"ai_pipeline_case_{index}_missing_transcript_source")

        if isinstance(transcript_file, str):
            transcript_path = cases_root / transcript_file
            transcript_payload = json.loads(transcript_path.read_text(encoding="utf-8"))
        else:
            transcript_payload = transcript_json

        if not isinstance(transcript_payload, dict):
            raise ValueError(f"ai_pipeline_case_{index}_transcript_must_be_object")
        cases.append(
            TranscriptCase(
                id=case_id.strip(),
                transcript_json=transcript_payload,
                notes=notes.strip() if isinstance(notes, str) else None,
            )
        )
    return cases


def select_cases(
    cases: list[TranscriptCase],
    *,
    count: int | None = None,
    last: int | None = None,
    case_id: str | None = None,
) -> list[TranscriptCase]:
    selected = cases
    if case_id:
        selected = [case for case in selected if case.id == case_id]
    if count is not None:
        selected = selected[:count]
    if last is not None:
        selected = selected[-last:]
    if case_id and not selected:
        raise ValueError(f"ai_pipeline_case_not_found: {case_id}")
    return selected


def build_turn_catalog(transcript_json: dict[str, object]) -> list[dict[str, object]]:
    catalog: list[dict[str, object]] = []
    chunks = transcript_json.get("chunks")
    if not isinstance(chunks, list):
        return catalog
    next_inferred_turn_id = 0
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        turns = chunk.get("turns")
        if not isinstance(turns, list):
            continue
        for turn in turns:
            if not isinstance(turn, dict):
                continue
            speaker = turn.get("speaker")
            text = turn.get("text")
            stored_turn_id = turn.get("turn_id")
            if not isinstance(speaker, str) or not isinstance(text, str):
                continue
            if isinstance(stored_turn_id, int):
                turn_id = stored_turn_id
                next_inferred_turn_id = max(next_inferred_turn_id, turn_id + 1)
            elif stored_turn_id is None:
                turn_id = next_inferred_turn_id
                next_inferred_turn_id += 1
            else:
                raise ValueError("ai_pipeline_turn_id_must_be_int_or_missing")
            catalog.append(
                {
                    "turn_id": turn_id,
                    "speaker": speaker,
                    "text": text,
                }
            )
    return catalog


def enumerate_turn_ids(transcript_json: dict[str, object]) -> list[int]:
    return list(range(len(build_turn_catalog(transcript_json))))


def render_user_payload(case: TranscriptCase) -> str:
    payload = {"turns": build_turn_catalog(case.transcript_json)}
    return json.dumps(payload, ensure_ascii=False, indent=2)
