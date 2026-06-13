from __future__ import annotations

from common.context_claims import ClaimAssignment
from common.templates import load_template
from context_pipeline.classify_claims.lib import (
    audit_claim_assignments,
    audit_claim_section_ids,
    parse_claim_classification_session_result,
)

AI_PIPELINE_ROOT = __import__("pathlib").Path(__file__).resolve().parents[3]
TEMPLATES_DIR = AI_PIPELINE_ROOT / "templates"


def test_audit_claim_section_ids_rejects_unknown_section() -> None:
    template = load_template("minimal_outpatient_v001", templates_dir=TEMPLATES_DIR)
    audit = audit_claim_section_ids(
        ClaimAssignment(claim_id="c1", section_ids=["not_a_section"]),
        template,
    )
    assert not audit.is_valid
    assert audit.unknown_section_ids == ["not_a_section"]


def test_parse_and_audit_claim_classification_session() -> None:
    template = load_template("minimal_outpatient_v001", templates_dir=TEMPLATES_DIR)
    raw = """
    {
      "assignments": [
        {"claim_id": "c1", "section_ids": ["antecedentes"]},
        {"claim_id": "c2", "section_ids": []}
      ]
    }
    """
    result = parse_claim_classification_session_result(raw)
    audit = audit_claim_assignments(result, ["c1", "c2"], template)
    assert audit.is_valid
