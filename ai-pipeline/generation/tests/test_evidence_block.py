from __future__ import annotations

from classification.lib import ClusterCase
from classification.templates import load_template
from generation.evidence_markers import CONTEXT_BRIEF_EVIDENCE_ID
from generation.lib import (
    SectionGenerationJob,
    collect_allowed_evidence_id_set,
    render_evidence_block,
)


def _cluster() -> ClusterCase:
    return ClusterCase(
        id="case1_a",
        template_id="minimal_outpatient_v001",
        cluster_json={
            "topic_label": "tema",
            "turns": [
                {"turn_id": 0, "speaker": "MEDICO", "text": "¿Dolor?"},
                {"turn_id": 1, "speaker": "PACIENTE", "text": "Sí."},
            ],
        },
    )


def test_render_evidence_block_formats_turns_spans_and_brief() -> None:
    template = load_template("minimal_outpatient_v001")
    section = next(
        s for s in template.sections if s.section_id == "motivo_consulta"
    )
    job = SectionGenerationJob(
        section_id=section.section_id,
        section=section,
        clusters=[_cluster()],
        context="Epicrisis previa: HTA.",
        evidence_spans=[
            {"id": "s3", "doc": "epicrisis", "text": "Neumonía resuelta."},
        ],
    )
    block = render_evidence_block(job)
    assert "Consulta actual:" in block
    assert "[t0] doctor: ¿Dolor?" in block
    assert "[t1] patient: Sí." in block
    assert "Contexto externo aprobado:" in block
    assert "[s3] epicrisis: Neumonía resuelta." in block
    assert f"[{CONTEXT_BRIEF_EVIDENCE_ID}] Epicrisis previa: HTA." in block


def test_collect_allowed_evidence_id_set_includes_c1() -> None:
    template = load_template("minimal_outpatient_v001")
    section = next(
        s for s in template.sections if s.section_id == "motivo_consulta"
    )
    job = SectionGenerationJob(
        section_id=section.section_id,
        section=section,
        clusters=[_cluster()],
        context="Brief.",
        evidence_spans=[{"id": "s1", "doc": "lab", "text": "Hb 12"}],
    )
    allowed = collect_allowed_evidence_id_set(job)
    assert allowed == {"t0", "t1", "s1", CONTEXT_BRIEF_EVIDENCE_ID}
