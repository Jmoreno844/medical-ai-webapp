from __future__ import annotations

import json
from typing import Any

import json

import pytest
from jsonschema import Draft202012Validator, ValidationError

from app.schema import CLINICAL_MENTIONS_SCHEMA, copy_clinical_mentions_schema


def _json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(schema))


def _validator(schema: dict[str, Any]) -> Draft202012Validator:
    return Draft202012Validator(_json_schema(schema))


def _validate(schema: dict[str, Any], instance: dict[str, Any]) -> None:
    _validator(schema).validate(instance)


def _validate_fails(schema: dict[str, Any], instance: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _validate(schema, instance)


def _empty_mentions() -> dict[str, Any]:
    return {"mentions": []}


def test_root_requires_mentions_only() -> None:
    mentions = _empty_mentions()
    _validate(CLINICAL_MENTIONS_SCHEMA, mentions)

    mentions["clinical_mentions"] = []
    _validate_fails(CLINICAL_MENTIONS_SCHEMA, mentions)


def test_mention_schema_accepts_null_subject_role() -> None:
    mentions = _empty_mentions()
    mentions["mentions"] = [
        {
            "entity_type": "clinical_concept",
            "entity_raw": "fiebre",
            "proposition_raw": "fiebre",
            "speech_act": "assertion",
            "subject_role": None,
            "attributes": [],
            "evidence": [{"quote": "fiebre", "turn_id": None}],
        }
    ]
    _validate(CLINICAL_MENTIONS_SCHEMA, mentions)


def test_mention_schema_accepts_deferred_action_and_patient_preference() -> None:
    mentions = _empty_mentions()
    mentions["mentions"] = [
        {
            "entity_type": "medication",
            "entity_raw": "aspirina",
            "proposition_raw": "No le mando aspirina todavia hasta no ver la ecografia",
            "speech_act": "deferred_action",
            "subject_role": "patient",
            "attributes": [],
            "evidence": [
                {
                    "quote": "No le mando aspirina todavia hasta no ver la ecografia",
                    "turn_id": "0:1",
                }
            ],
        },
        {
            "entity_type": "care_instruction",
            "entity_raw": "incapacidad",
            "proposition_raw": "no me vaya a incapacitar",
            "speech_act": "patient_preference",
            "subject_role": "patient",
            "attributes": [],
            "evidence": [{"quote": "no me vaya a incapacitar", "turn_id": "1:0"}],
        },
    ]
    _validate(CLINICAL_MENTIONS_SCHEMA, mentions)


def test_mention_schema_accepts_v2_shape() -> None:
    mentions = _empty_mentions()
    mentions["mentions"] = [
        {
            "entity_type": "medication",
            "entity_raw": "ibuprofeno",
            "proposition_raw": "No tome ibuprofeno",
            "speech_act": "instruction_to_avoid",
            "subject_role": "patient",
            "attributes": [],
            "evidence": [{"quote": "No tome ibuprofeno", "turn_id": "0:1"}],
        }
    ]
    _validate(CLINICAL_MENTIONS_SCHEMA, mentions)


def test_schema_rejects_legacy_v11_fields() -> None:
    mentions = _empty_mentions()
    mentions["mentions"] = [
        {
            "raw_text_span": "ibuprofeno",
            "category": "medication",
            "linguistic_polarity": "negative",
            "temporal_reference": "proposed_future",
            "speaker": "clinician",
            "parameters": [],
            "evidence": [{"quote": "No tome ibuprofeno", "turn_id": "0:1"}],
        }
    ]
    _validate_fails(CLINICAL_MENTIONS_SCHEMA, mentions)


def test_schema_rejects_object_evidence_and_unknown_attribute_kind() -> None:
    mentions = _empty_mentions()
    mentions["mentions"] = [
        {
            "entity_type": "medication",
            "entity_raw": "losartan",
            "proposition_raw": "losartan de cien",
            "speech_act": "correction",
            "subject_role": "patient",
            "attributes": [{"kind": "other_explicit", "raw_text": "cien"}],
            "evidence": {"quote": "losartan de cien", "turn_id": "0:1"},
        }
    ]
    _validate_fails(CLINICAL_MENTIONS_SCHEMA, mentions)


def test_schema_uses_anyof_for_nullable_fields() -> None:
    mention_schema = CLINICAL_MENTIONS_SCHEMA["properties"]["mentions"]["items"]
    subject_role = mention_schema["properties"]["subject_role"]
    turn_id = mention_schema["properties"]["evidence"]["items"]["properties"]["turn_id"]

    assert subject_role["anyOf"] == [
        {
            "type": "string",
            "enum": [
                "patient",
                "companion",
                "family_member",
                "clinician",
                "other_explicit",
            ],
        },
        {"type": "null"},
    ]
    assert turn_id["anyOf"] == [{"type": "string"}, {"type": "null"}]


def test_schema_has_titles_and_descriptions() -> None:
    assert CLINICAL_MENTIONS_SCHEMA["title"] == "ClinicalMentionsV2"
    mention_schema = CLINICAL_MENTIONS_SCHEMA["properties"]["mentions"]["items"]
    assert "description" in CLINICAL_MENTIONS_SCHEMA
    assert "title" in mention_schema
    assert "description" in mention_schema
    assert "description" in mention_schema["properties"]["entity_type"]
    assert "description" in mention_schema["properties"]["speech_act"]


def test_gemini_schema_transform_does_not_mutate_module_schema() -> None:
    from google.genai import _transformers

    before = json.dumps(CLINICAL_MENTIONS_SCHEMA)
    _transformers.process_schema(copy_clinical_mentions_schema(), client=None)
    after = json.dumps(CLINICAL_MENTIONS_SCHEMA)

    assert before == after
    assert "propertyOrdering" not in after
