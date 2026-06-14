from __future__ import annotations

import json

import pytest

from common.templates import compose_section_guidelines, load_template


def test_load_template_splits_classification_and_generation_guidelines() -> None:
    template = load_template("minimal_outpatient_v001")
    assert template.classification.guidelines
    assert template.generation.guidelines
    assert template.classification.guidelines != template.generation.guidelines

    section = template.section_by_id("motivo_consulta")
    assert section is not None
    assert section.classification.guidelines
    assert section.generation.guidelines
    assert section.classification.guidelines != section.generation.guidelines


def test_to_classification_prompt_payload_uses_classification_guidelines() -> None:
    template = load_template("minimal_outpatient_v001")
    payload = template.to_classification_prompt_payload()
    assert payload["guidelines"] == template.classification.guidelines
    section_payload = payload["sections"][0]
    assert isinstance(section_payload, dict)
    section = template.sections[0]
    assert section_payload["guidelines"] == section.classification.guidelines
    assert "generation" not in section_payload


def test_section_generation_payload_shape() -> None:
    from classification.lib import ClusterCase, cluster_to_payload_item
    from generation.lib import render_section_user_payload

    template = load_template("minimal_outpatient_v001")
    section = template.section_by_id("motivo_consulta")
    assert section is not None
    cluster = ClusterCase(
        id="case1_a",
        template_id="minimal_outpatient_v001",
        cluster_json={
            "topic_label": "cansancio",
            "turns": [{"turn_id": 0, "speaker": "PACIENTE", "text": "me canso"}],
        },
    )
    raw = render_section_user_payload(
        section=section,
        clusters=[cluster],
        template=template,
    )
    payload = json.loads(raw)
    assert payload["template_guidelines"] == template.generation.guidelines
    assert payload["section"]["guidelines"] == section.generation.guidelines
    assert payload["clusters"] == [cluster_to_payload_item(cluster)]


def test_outpatient_general_template_loads_with_seventeen_sections() -> None:
    template = load_template("outpatient_general_v001")
    assert template.id == "outpatient_general_v001"
    assert template.name == "Consulta externa general (R&D)"
    assert len(template.sections) == 17
    assert template.section_by_id("estudios_y_resultados") is not None
    assert template.section_by_id("comprension_plan") is not None


def test_consulta_estructurada_template_loads_with_nine_sections() -> None:
    template = load_template("consulta_estructurada_v001")
    assert template.id == "consulta_estructurada_v001"
    assert len(template.sections) == 9
    assert template.section_by_id("revision_sistemas") is not None
    assert template.section_by_id("analisis_y_plan") is not None
    signos = template.section_by_id("signos_vitales")
    assert signos is not None
    assert "Presión arterial sistólica" in signos.generation.guidelines
    assert signos.to_generation_payload()["guidelines"] == signos.generation.guidelines


def test_consulta_estructurada_v002_loads_with_ten_sections() -> None:
    template = load_template("consulta_estructurada_v002")
    assert template.id == "consulta_estructurada_v002"
    assert template.name == "Consulta estructurada (R&D) v2"
    assert len(template.sections) == 10
    assert template.section_by_id("antecedentes_gineco_obstetricos") is not None
    estudios = template.section_by_id("estudios_y_resultados")
    assert estudios is not None
    assert "ECG" in estudios.include
    assert "biopsia" in estudios.include


def test_compose_section_guidelines_with_include_and_boundaries() -> None:
    section = load_template("consulta_estructurada_v002").section_by_id("signos_vitales")
    assert section is not None
    guidelines = section.to_generation_payload()["guidelines"]
    assert isinstance(guidelines, str)
    assert "Incluye:" in guidelines
    assert "Límites:" in guidelines
    assert "casa" in guidelines


def test_compose_section_guidelines_empty_returns_raw() -> None:
    assert compose_section_guidelines("raw guideline", "", "") == "raw guideline"
    section = load_template("minimal_outpatient_v001").section_by_id("motivo_consulta")
    assert section is not None
    assert section.to_generation_payload()["guidelines"] == section.generation.guidelines
    assert section.to_classification_payload()["guidelines"] == section.classification.guidelines


def test_template_rejects_duplicate_section_ids(tmp_path) -> None:
    path = tmp_path / "dup.json"
    path.write_text(
        json.dumps(
            {
                "id": "dup",
                "name": "dup",
                "document_kind": "document",
                "sections": [
                    {
                        "section_id": "a",
                        "heading": "A",
                        "description": "d",
                    },
                    {
                        "section_id": "a",
                        "heading": "A2",
                        "description": "d2",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="clinical_template_invalid"):
        load_template("dup", templates_dir=tmp_path)
