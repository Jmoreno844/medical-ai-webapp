from __future__ import annotations

import pytest

from generation.evidence_markers import (
    audit_evidence_markers,
    extract_all_marker_ids,
    extract_marker_id_sets,
    parse_linked_plaintext,
)


def test_extract_marker_id_sets() -> None:
    text = (
        "Cefalea de 3 días. {{e:t3,t4}}\n"
        "- Epicrisis previa. {{e:s1}}\n"
    )
    assert extract_marker_id_sets(text) == [{"t3", "t4"}, {"s1"}]
    assert extract_all_marker_ids(text) == {"t3", "t4", "s1"}


def test_audit_evidence_markers_rejects_unknown_id() -> None:
    with pytest.raises(ValueError, match="unknown_evidence_marker_ids"):
        audit_evidence_markers(
            "Dato clínico. {{e:s99}}",
            {"t0", "s1"},
        )


def test_parse_linked_plaintext_strips_fences() -> None:
    raw = "```markdown\nCefalea. {{e:t0}}\n```"
    assert parse_linked_plaintext(raw) == "Cefalea. {{e:t0}}"
