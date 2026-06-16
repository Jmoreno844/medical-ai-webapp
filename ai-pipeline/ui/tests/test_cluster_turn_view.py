from __future__ import annotations

from ui.components.viewers import (
    _cluster_turn_dicts,
    _cluster_turn_scroll_height,
    _format_turn_speaker_label,
)


def test_format_turn_speaker_label_includes_turn_id() -> None:
    label = _format_turn_speaker_label(
        {"speaker": "Médico", "turn_id": 12, "text": "Hola"},
    )
    assert label == "Médico · turn 12"


def test_cluster_turn_dicts_filters_non_dict_rows() -> None:
    turns = [{"speaker": "Paciente", "text": "Sí"}, "bad", None]
    assert _cluster_turn_dicts(turns) == [{"speaker": "Paciente", "text": "Sí"}]


def test_cluster_turn_scroll_height_caps_long_clusters() -> None:
    assert _cluster_turn_scroll_height(2) == 160
    assert _cluster_turn_scroll_height(20) == 480
