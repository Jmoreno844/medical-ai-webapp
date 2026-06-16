from __future__ import annotations

from document_pipeline_core.generation.lib import format_section_output_for_detail

from ui.components import viewers as viewers_module
from ui.components.viewers import (
    CONTENT_VIEW_APPLIED,
    CONTENT_VIEW_SOURCE,
    _render_generation_document_sections,
    _render_generation_section_body,
)


class _FakeStreamlit:
    def __init__(self) -> None:
        self.markdown_calls: list[str] = []
        self.code_calls: list[str] = []
        self.caption_calls: list[str] = []

    def markdown(self, text: str, **_kwargs: object) -> None:
        self.markdown_calls.append(text)

    def code(self, text: str, **_kwargs: object) -> None:
        self.code_calls.append(text)

    def caption(self, text: str) -> None:
        self.caption_calls.append(text)


def _patch_viewer_dependencies(monkeypatch, fake_st: _FakeStreamlit) -> None:
    monkeypatch.setattr(viewers_module, "st", fake_st)
    monkeypatch.setattr(
        viewers_module,
        "_render_generation_section_actions",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        viewers_module,
        "_render_linked_evidence_audit",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        viewers_module,
        "_render_cluster_planner_audit",
        lambda **_kwargs: None,
    )


def test_generation_section_body_shows_heading_in_applied_view(
    monkeypatch,
) -> None:
    fake_st = _FakeStreamlit()
    _patch_viewer_dependencies(monkeypatch, fake_st)

    _render_generation_section_body(
        payload={},
        section={
            "section_id": "motivo_consulta",
            "heading": "Motivo de consulta",
            "content": "Dolor leve.",
        },
        section_index=0,
        section_outputs_by_id={},
        key_suffix="test",
        content_view_mode=CONTENT_VIEW_APPLIED,
        show_evidence_ids=False,
        document_wrapper=False,
    )

    assert any("## Motivo de consulta" in text for text in fake_st.markdown_calls)
    assert any("Dolor leve." in text for text in fake_st.markdown_calls)


def test_generation_section_body_shows_heading_in_source_view(
    monkeypatch,
) -> None:
    fake_st = _FakeStreamlit()
    _patch_viewer_dependencies(monkeypatch, fake_st)

    _render_generation_section_body(
        payload={},
        section={
            "section_id": "motivo_consulta",
            "heading": "Motivo de consulta",
            "content": "Dolor leve.",
        },
        section_index=0,
        section_outputs_by_id={},
        key_suffix="test",
        content_view_mode=CONTENT_VIEW_SOURCE,
        show_evidence_ids=False,
        document_wrapper=False,
    )

    assert any("## Motivo de consulta" in text for text in fake_st.markdown_calls)
    assert fake_st.code_calls == ["Dolor leve."]


def test_generation_section_body_shows_heading_for_empty_section(
    monkeypatch,
) -> None:
    fake_st = _FakeStreamlit()
    _patch_viewer_dependencies(monkeypatch, fake_st)

    _render_generation_section_body(
        payload={},
        section={
            "section_id": "motivo_consulta",
            "heading": "Motivo de consulta",
            "content": "",
        },
        section_index=0,
        section_outputs_by_id={},
        key_suffix="test",
        content_view_mode=CONTENT_VIEW_APPLIED,
        show_evidence_ids=False,
        document_wrapper=False,
    )

    assert any("## Motivo de consulta" in text for text in fake_st.markdown_calls)
    assert "*(vacío)*" in fake_st.caption_calls


def test_generation_document_sections_show_evidence_checkbox_for_cluster_planner(
    monkeypatch,
) -> None:
    fake_st = _FakeStreamlit()
    fake_st.checkbox_calls: list[str] = []

    def checkbox(label: str, **_kwargs: object) -> bool:
        fake_st.checkbox_calls.append(label)
        return False

    fake_st.checkbox = checkbox
    fake_st.radio = lambda *_args, **_kwargs: CONTENT_VIEW_APPLIED
    fake_st.markdown = lambda *_args, **_kwargs: None
    monkeypatch.setattr(viewers_module, "st", fake_st)
    monkeypatch.setattr(
        viewers_module,
        "_render_generation_section_body",
        lambda **_kwargs: None,
    )

    payload = {
        "generation_session_result": {
            "sections": [
                {
                    "section_id": "enfermedad_actual",
                    "heading": "Enfermedad actual",
                    "content": "Evolución. {{e:t0}}",
                }
            ]
        },
        "section_outputs": [
            {
                "section_id": "enfermedad_actual",
                "generation_route": "cluster_planner",
            }
        ],
    }
    _render_generation_document_sections(payload, key_suffix="test_cp", document_wrapper=False)
    assert "Mostrar IDs de evidencia" in fake_st.checkbox_calls


def test_section_uses_inline_evidence_markers_includes_cluster_planner() -> None:
    from ui.linked_evidence_audit import section_uses_inline_evidence_markers

    assert section_uses_inline_evidence_markers(
        {"generation_route": "cluster_planner"},
    )
    assert not section_uses_inline_evidence_markers(
        {"generation_route": "direct"},
    )


def test_format_section_output_preserves_renderer_skipped_in_compact() -> None:
    section_output = {
        "section_id": "motivo_consulta",
        "generation_route": "cluster_planner",
        "renderer_skipped": True,
        "generation_result": {"section_id": "motivo_consulta", "content": ""},
    }
    compact = format_section_output_for_detail(section_output, "compact")
    assert compact.get("renderer_skipped") is True


def test_generation_document_sections_show_evidence_checkbox_for_direct_with_evidence(
    monkeypatch,
) -> None:
    fake_st = _FakeStreamlit()
    fake_st.checkbox_calls: list[str] = []

    def checkbox(label: str, **_kwargs: object) -> bool:
        fake_st.checkbox_calls.append(label)
        return False

    fake_st.checkbox = checkbox
    fake_st.radio = lambda *_args, **_kwargs: CONTENT_VIEW_APPLIED
    fake_st.markdown = lambda *_args, **_kwargs: None
    monkeypatch.setattr(viewers_module, "st", fake_st)
    monkeypatch.setattr(
        viewers_module,
        "_render_generation_section_body",
        lambda **_kwargs: None,
    )

    payload = {
        "generation_session_result": {
            "sections": [
                {
                    "section_id": "motivo_consulta",
                    "heading": "Motivo de consulta",
                    "content": "Dolor. {{e:t0}}",
                }
            ]
        },
        "section_outputs": [
            {
                "section_id": "motivo_consulta",
                "generation_route": "direct_with_evidence",
            }
        ],
    }
    _render_generation_document_sections(payload, key_suffix="test", document_wrapper=False)
    assert "Mostrar IDs de evidencia" in fake_st.checkbox_calls

