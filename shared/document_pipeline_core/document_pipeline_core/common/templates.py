from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, model_validator

from document_pipeline_core.package_root import CORE_PACKAGE_ROOT, DEFAULT_TEMPLATES_DIR


class StepGuidelines(BaseModel):
    guidelines: str = ""
    mode: str = ""
    preferred_route: str = ""


_SECTION_GENERATION_MODE_BY_ID: dict[str, str] = {
    "motivo_consulta": "short_single_field",
    "enfermedad_actual": "narrative",
    "revision_sistemas": "items_by_system",
    "antecedentes": "single_fields",
    "antecedentes_gineco_obstetricos": "single_fields",
    "signos_vitales": "single_fields",
    "examen_fisico": "items_by_region",
    "estudios_y_resultados": "structured_items",
    "analisis_y_plan": "mixed_clinical_items",
    "analisis_clinico": "mixed_clinical_items",
    "identificacion": "single_fields",
}


def resolve_generation_mode(section: TemplateSection) -> str:
    configured = section.generation.mode.strip()
    if configured:
        return configured
    return _SECTION_GENERATION_MODE_BY_ID.get(section.section_id, "narrative")


def compose_section_guidelines(
    raw: str,
    include: str,
    boundaries: str,
) -> str:
    include_text = include.strip()
    boundaries_text = boundaries.strip()
    raw_text = raw.strip()
    if not include_text and not boundaries_text:
        return raw
    parts: list[str] = []
    if include_text:
        parts.append(f"Incluye:\n{include_text}")
    if boundaries_text:
        parts.append(f"Límites:\n{boundaries_text}")
    if raw_text:
        parts.append(raw_text)
    return "\n\n".join(parts)


class TemplateSection(BaseModel):
    section_id: str
    heading: str
    description: str
    include: str = ""
    boundaries: str = ""
    classification: StepGuidelines = Field(default_factory=StepGuidelines)
    generation: StepGuidelines = Field(default_factory=StepGuidelines)

    def to_classification_payload(self) -> dict[str, object]:
        return {
            "section_id": self.section_id,
            "heading": self.heading,
            "description": self.description,
            "guidelines": compose_section_guidelines(
                self.classification.guidelines,
                self.include,
                self.boundaries,
            ),
        }

    def to_generation_payload(self) -> dict[str, object]:
        return {
            "section_id": self.section_id,
            "heading": self.heading,
            "description": self.description,
            "guidelines": compose_section_guidelines(
                self.generation.guidelines,
                self.include,
                self.boundaries,
            ),
        }


class ClinicalTemplate(BaseModel):
    id: str
    name: str
    document_kind: str
    classification: StepGuidelines = Field(default_factory=StepGuidelines)
    generation: StepGuidelines = Field(default_factory=StepGuidelines)
    sections: list[TemplateSection] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_section_ids(self) -> ClinicalTemplate:
        section_ids = [section.section_id for section in self.sections]
        if len(section_ids) != len(set(section_ids)):
            raise ValueError("clinical_template_duplicate_section_id")
        return self

    def section_id_set(self) -> set[str]:
        return {section.section_id for section in self.sections}

    def headings_by_section_id(self) -> dict[str, str]:
        return {section.section_id: section.heading for section in self.sections}

    def section_by_id(self, section_id: str) -> TemplateSection | None:
        for section in self.sections:
            if section.section_id == section_id:
                return section
        return None

    def to_classification_prompt_payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "guidelines": self.classification.guidelines,
            "sections": [
                section.to_classification_payload() for section in self.sections
            ],
        }

    def to_prompt_payload(self) -> dict[str, object]:
        return self.to_classification_prompt_payload()


ClassificationTemplate = ClinicalTemplate

HYBRID_GENERATION_TEMPLATE_IDS = frozenset({"consulta_estructurada_v001"})
SECTION_GENERATION_PREFERRED_ROUTES = frozenset(
    {"direct_with_evidence", "cluster_planner"},
)


def template_supports_hybrid_generation(template: ClinicalTemplate) -> bool:
    if template.id not in HYBRID_GENERATION_TEMPLATE_IDS:
        return False
    if not template.sections:
        return False
    for section in template.sections:
        preferred_route = section.generation.preferred_route.strip()
        if preferred_route not in SECTION_GENERATION_PREFERRED_ROUTES:
            return False
    return True


def template_supports_hybrid_generation_by_id(
    template_id: str,
    *,
    templates_dir: Path = DEFAULT_TEMPLATES_DIR,
) -> bool:
    normalized = template_id.strip()
    if not normalized:
        return False
    try:
        template = load_template(normalized, templates_dir=templates_dir)
    except (FileNotFoundError, ValueError):
        return False
    return template_supports_hybrid_generation(template)


def template_file_path(*, templates_dir: Path, template_id: str) -> Path:
    normalized = template_id.strip()
    if not normalized:
        raise ValueError("clinical_template_id_must_be_non_empty")
    return templates_dir / f"{normalized}.json"


def load_template(
    template_id: str,
    *,
    templates_dir: Path = DEFAULT_TEMPLATES_DIR,
) -> ClinicalTemplate:
    path = template_file_path(templates_dir=templates_dir, template_id=template_id)
    if not path.is_file():
        raise FileNotFoundError(f"clinical_template_not_found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    try:
        return ClinicalTemplate.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"clinical_template_invalid: {exc}") from exc


def list_template_ids(*, templates_dir: Path = DEFAULT_TEMPLATES_DIR) -> list[str]:
    if not templates_dir.is_dir():
        return []
    return sorted(path.stem for path in templates_dir.glob("*.json"))


__all__ = [
    "CORE_PACKAGE_ROOT",
    "ClassificationTemplate",
    "ClinicalTemplate",
    "DEFAULT_TEMPLATES_DIR",
    "StepGuidelines",
    "TemplateSection",
    "compose_section_guidelines",
    "HYBRID_GENERATION_TEMPLATE_IDS",
    "resolve_generation_mode",
    "SECTION_GENERATION_PREFERRED_ROUTES",
    "template_supports_hybrid_generation",
    "template_supports_hybrid_generation_by_id",
    "load_template",
    "template_file_path",
]
