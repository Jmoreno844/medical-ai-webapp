from __future__ import annotations

from ui.components.viewers import _id_text_rows


def test_id_text_rows_without_truncation() -> None:
    rows = _id_text_rows(
        [{"id": "1", "text": "x" * 200}],
        truncate_at=None,
    )
    assert len(rows) == 1
    assert rows[0]["text"] == "x" * 200


def test_id_text_rows_truncates_when_requested() -> None:
    rows = _id_text_rows(
        [{"id": "1", "text": "abcdefghijklmnop"}],
        truncate_at=10,
    )
    assert rows[0]["text"] == "abcdefg..."
