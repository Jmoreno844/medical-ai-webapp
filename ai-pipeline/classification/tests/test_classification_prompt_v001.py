from __future__ import annotations

import json

from classification.lib import ClusterCase, cluster_to_payload_item
from classification.prompts.classification_prompt_v001 import SYSTEM_PROMPT, output_schema, render_user_payload
from classification.templates import load_template


def _demo_cluster() -> dict[str, object]:
    cluster = ClusterCase(
        id="case1_demo",
        template_id="consulta_estructurada_v001",
        cluster_json={
            "topic_label": "demo",
            "turns": [{"turn_id": 0, "speaker": "PACIENTE", "text": "me duele el pecho"}],
        },
    )
    return cluster_to_payload_item(cluster)


def test_system_prompt_not_empty() -> None:
    assert SYSTEM_PROMPT.strip()
    assert "# Output contract" in SYSTEM_PROMPT


def test_render_user_payload_emits_four_blocks() -> None:
    template = load_template("consulta_estructurada_v001")
    payload = render_user_payload(template=template, clusters=[_demo_cluster()])
    assert "<template_ref>" in payload
    assert "<template_classification_guidelines>" in payload
    assert "<allowed_sections>" in payload
    assert "<clusters>" in payload
    assert payload.index("</template_ref>") < payload.index("<allowed_sections>")
    assert payload.index("</allowed_sections>") < payload.index("<clusters>")


def test_render_user_payload_clusters_json_valid() -> None:
    template = load_template("consulta_estructurada_v001")
    payload = render_user_payload(template=template, clusters=[_demo_cluster()])
    clusters_start = payload.index("<clusters>") + len("<clusters>\n")
    clusters_end = payload.index("</clusters>")
    clusters_json = json.loads(payload[clusters_start:clusters_end].strip())
    assert clusters_json[0]["cluster_id"] == "case1_demo"
    assert clusters_json[0]["turns"][0]["text"] == "me duele el pecho"


def test_render_user_payload_sections_have_classification_guidelines() -> None:
    template = load_template("consulta_estructurada_v001")
    payload = render_user_payload(template=template, clusters=[_demo_cluster()])
    assert '<section id="signos_vitales">' in payload
    assert "Title: Signos vitales" in payload
    assert "Description:" in payload
    assert "Classification guidelines:" in payload
    assert "Incluye:" in payload
    assert "generation" not in payload.lower()


def test_output_schema_enum_matches_template_sections() -> None:
    template = load_template("consulta_estructurada_v001")
    schema = output_schema(template)
    enum_values = schema["properties"]["assignments"]["items"]["properties"][
        "section_ids"
    ]["items"]["enum"]
    assert sorted(enum_values) == sorted(template.section_id_set())
    assert schema["additionalProperties"] is False
