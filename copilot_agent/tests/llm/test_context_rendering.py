from app.llm.context_rendering import render_patch_input, render_turn_context
from tests.fixtures_copilot import build_state


def test_render_turn_context_keeps_workspace_and_budget_sections():
    state = build_state("resume el encounter actual")
    state["available_documents"] = [
        {
            "document_id": "99",
            "title": "Nota clinica",
            "type": "note",
            "status": "draft",
            "version": 3,
            "is_active": True,
            "is_open": True,
            "ai_writable": True,
            "excerpt": "Paciente estable.",
        }
    ]
    state["document_summaries"] = {
        "99": {
            "title": "Nota clinica",
            "type": "note",
            "version": 3,
            "short_summary": "Paciente estable.",
            "excerpt": "Paciente estable.",
        }
    }
    state["read_spans"] = [
        {
            "document_id": "99",
            "title": "Nota clinica",
            "start_offset": 0,
            "end_offset": 17,
            "content": "Paciente estable.",
        }
    ]
    state["context_view"] = {
        "facts": [
            {
                "category": "plan",
                "value": "Seguimiento en 48 horas.",
                "source_document_id": "12",
                "confidence": 0.8,
            }
        ]
    }
    state["patch_history"] = {
        "99": [
            {
                "patch_id": "patch-1",
                "status": "pending",
                "operation_type": "replace_span",
                "rationale": "Actualizar nota.",
            }
        ]
    }
    state["search_matches"] = [
        {
            "document_id": "77",
            "title": "Epicrisis",
            "score": 0.8,
            "snippet": "Coincidencia relevante.",
        }
    ]

    rendered = render_turn_context(state)

    assert "<copilot_turn_context>" in rendered
    assert "<workspace_index>" in rendered
    assert "<available_documents>" in rendered
    assert "<document_summaries>" in rendered
    assert "<read_spans>" in rendered
    assert "<context_view>" in rendered
    assert "<search_matches>" in rendered
    assert "<patch_history>" in rendered
    assert "<budgets>" in rendered


def test_render_patch_input_keeps_target_span_and_supporting_context():
    rendered = render_patch_input(
        state=build_state("agrega el antecedente relevante"),
        target_document={
            "document_id": "99",
            "title": "Nota clinica",
            "type": "note",
            "version": 3,
        },
        target_document_content="Paciente estable.",
        supporting_context=[
            {
                "document_id": "12",
                "title": "Contexto del encuentro",
                "type": "context",
                "read_mode": "context_view",
                "excerpt": "Alergia a penicilina.",
            }
        ],
        span_payload={
            "start_offset": 0,
            "end_offset": 17,
            "content_hash": "hash-demo",
        },
        requested_tool_name="propose_replace_span",
    )

    assert "<patch_drafting_input>" in rendered
    assert "<requested_tool_name>propose_replace_span</requested_tool_name>" in rendered
    assert "<target_document>" in rendered
    assert "<selected_span>" in rendered
    assert "<supporting_context>" in rendered
    assert "Alergia a penicilina." in rendered
