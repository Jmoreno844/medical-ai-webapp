from __future__ import annotations

from copy import deepcopy
from typing import Any


def _object_schema(
    *,
    title: str,
    description: str,
    properties: dict[str, Any],
) -> dict[str, Any]:
    return {
        "title": title,
        "description": description,
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(properties),
    }


def _nullable_string(*, title: str, description: str) -> dict[str, Any]:
    return {
        "title": title,
        "description": description,
        "anyOf": [
            {"type": "string"},
            {"type": "null"},
        ],
    }


def _nullable_enum(
    values: list[str],
    *,
    title: str,
    description: str,
) -> dict[str, Any]:
    return {
        "title": title,
        "description": description,
        "anyOf": [
            {"type": "string", "enum": values},
            {"type": "null"},
        ],
    }


def _array(
    items: dict[str, Any],
    *,
    title: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "array", "items": items}
    if title:
        schema["title"] = title
    if description:
        schema["description"] = description
    return schema


EVIDENCE_ITEM_SCHEMA: dict[str, Any] = _object_schema(
    title="MentionEvidence",
    description="Single-turn verbatim evidence used to ground one mention.",
    properties={
        "quote": {
            "title": "Verbatim Quote",
            "description": "Exact contiguous transcript text from one turn; do not normalize or summarize it.",
            "type": "string",
        },
        "turn_id": _nullable_string(
            title="Turn Hint",
            description=(
                "Turn identifier that points to the quoted turn; it is a hint for "
                "grounding, not a substitute for the quote."
            ),
        ),
    },
)

ATTRIBUTE_SCHEMA: dict[str, Any] = _object_schema(
    title="MentionAttribute",
    description="Sensitive attribute text that stays attached to the same proposition instead of becoming a separate mention.",
    properties={
        "kind": {
            "title": "Attribute Kind",
            "description": "Literal attribute role. Use correction kinds only for explicit repair language or replaced values; do not infer units or semantics.",
            "type": "string",
            "enum": [
                "dose_value",
                "dose_unit",
                "route",
                "frequency",
                "duration",
                "measurement_value",
                "measurement_unit",
                "result_text",
                "prior_value",
                "replacement_value",
                "repair_language",
            ],
        },
        "raw_text": {
            "title": "Attribute Text",
            "description": "Exact text span for the attribute as spoken in the evidence quote.",
            "type": "string",
        },
    },
)

MENTION_SCHEMA: dict[str, Any] = _object_schema(
    title="ClinicalMention",
    description="Atomic clinical proposition with one entity focus, one speech act, optional sensitive attributes, and grounded evidence.",
    properties={
        "entity_type": {
            "title": "Entity Type",
            "description": "Entity family being discussed. Choose clinical_concept for symptoms, conditions, impressions, or non-medication clinical content.",
            "type": "string",
            "enum": [
                "clinical_concept",
                "medication",
                "allergy",
                "diagnostic_test",
                "measurement",
                "procedure",
                "care_instruction",
            ],
        },
        "entity_raw": {
            "title": "Entity Text",
            "description": "Literal text span naming the main entity, kept narrower than proposition_raw when possible.",
            "type": "string",
        },
        "proposition_raw": {
            "title": "Proposition Text",
            "description": "Literal text span for the whole atomic proposition, including the entity and any attached meaning that belongs to the same speech act.",
            "type": "string",
        },
        "speech_act": {
            "title": "Speech Act",
            "description": (
                "How the proposition is stated. Use 'instruction_to_avoid' ONLY for strict "
                "medical prohibitions. Use 'deferred_action' for things postponed, and "
                "'patient_preference' for patient requests."
            ),
            "type": "string",
            "enum": [
                "assertion",
                "negation",
                "uncertain_statement",
                "question",
                "hypothesis",
                "prescription",
                "order",
                "instruction_to_avoid",
                "deferred_action",
                "patient_preference",
                "conditional_instruction",
                "reported_result",
                "pending_result",
                "correction",
            ],
        },
        "subject_role": _nullable_enum(
            [
                "patient",
                "companion",
                "family_member",
                "clinician",
                "other_explicit",
            ],
            title="Subject Role",
            description=(
                "Who the proposition is about relative to the encounter focus. Keep it "
                "minimal and explicit; use null when the subject is not clear."
            ),
        ),
        "attributes": _array(
            ATTRIBUTE_SCHEMA,
            title="Mention Attributes",
            description="Literal subspans that remain attached to the same proposition, such as dose, duration, result text, or correction values.",
        ),
        "evidence": _array(
            EVIDENCE_ITEM_SCHEMA,
            title="Mention Evidence",
            description="One primary evidence item is preferred, but the contract allows a list for grounding stability.",
        ),
    },
)

CLINICAL_MENTIONS_SCHEMA: dict[str, Any] = _object_schema(
    title="ClinicalMentionsV2",
    description="List of atomic grounded clinical propositions for debug and future shadow extraction.",
    properties={
        "mentions": _array(
            MENTION_SCHEMA,
            title="Mentions",
            description="Atomic propositions extracted from the encounter transcript.",
        ),
    },
)


def copy_clinical_mentions_schema() -> dict[str, Any]:
    return deepcopy(CLINICAL_MENTIONS_SCHEMA)
