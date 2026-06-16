from __future__ import annotations

from common.context_spans import DoctorItem
from context_pipeline.triage.prompts import triage_prompt_v001


def test_render_user_payload_includes_manifest() -> None:
    payload = triage_prompt_v001.render_user_payload(
        session_id="s1",
        items=[{"id": 1, "text": "Paciente con diabetes."}],
        available_documents=["case2_labs"],
        template_section_ids=["antecedentes", "motivo_consulta"],
    )
    assert "manifest" in payload
    assert "case2_labs" in payload
    assert "antecedentes" in payload


def test_output_schema_directive_scopes() -> None:
    schema = triage_prompt_v001.output_schema(item_ids=[])
    directive = schema["properties"]["directives"]["items"]
    variants = directive["oneOf"]
    actions_by_scope = {
        (variant["properties"]["scope"]["const"], variant["properties"]["action"]["const"])
        for variant in variants
    }

    assert ("document", "ignore_source") in actions_by_scope
    assert ("document", "limit_source_to") in actions_by_scope
    assert ("transcript", "limit_to_topic") in actions_by_scope
    assert ("transcript", "ignore_source") not in actions_by_scope
    assert ("generation", "apply_instruction") in actions_by_scope


def test_output_schema_requires_fields_by_directive_action() -> None:
    schema = triage_prompt_v001.output_schema(item_ids=[])
    variants = schema["properties"]["directives"]["items"]["oneOf"]

    by_action = {
        (variant["properties"]["scope"]["const"], variant["properties"]["action"]["const"]): variant
        for variant in variants
    }

    assert by_action[("document", "limit_source_to")]["required"] == [
        "scope",
        "action",
        "target",
        "topic",
    ]
    assert by_action[("document", "prefer_topic")]["required"] == [
        "scope",
        "action",
        "topic",
    ]
    assert by_action[("transcript", "limit_to_topic")]["required"] == [
        "scope",
        "action",
        "topic",
        "section_id",
    ]
