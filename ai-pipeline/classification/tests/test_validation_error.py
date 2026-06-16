from __future__ import annotations

from classification.lib import ClassificationValidationError, audit_batch_assignments
from classification.lib import ClassificationBatchResult, ClusterAssignment
from classification.templates import load_template
from common.templates import DEFAULT_TEMPLATES_DIR


def test_audit_batch_assignments_invalid_section_includes_section_ids() -> None:
    template = load_template("minimal_outpatient_v001", templates_dir=DEFAULT_TEMPLATES_DIR)
    result = audit_batch_assignments(
        ClassificationBatchResult(
            assignments=[
                ClusterAssignment(
                    cluster_id="c1",
                    section_ids=["not_a_real_section"],
                )
            ]
        ),
        ["c1"],
        template,
    )
    assert result.invalid_section_cluster_ids == ["c1"]
    assert result.invalid_section_assignments[0]["cluster_id"] == "c1"
    assert result.invalid_section_assignments[0]["unknown_section_ids"] == [
        "not_a_real_section"
    ]


def test_classification_validation_error_diagnostics() -> None:
    exc = ClassificationValidationError(
        "classification_invalid_section_ids: cluster_id='c1' unknown_section_ids=['bad']",
        raw_response='{"assignments":[]}',
        classification_result={"assignments": []},
        batch_assignment_audit={"invalid_section_cluster_ids": ["c1"]},
        cluster_ids=["c1", "c2"],
    )
    diagnostics = exc.diagnostics()
    assert diagnostics["raw_response"] == '{"assignments":[]}'
    assert diagnostics["cluster_ids"] == ["c1", "c2"]
    assert "unknown_section_ids" in str(exc)
