from app.llm.context_rendering import render_patch_input, render_turn_context
from tests.fixtures_copilot import build_state


def test_render_turn_context_keeps_workspace_and_relevant_context_sections():
    state = build_state("resume el encounter actual")
    state["workspace_index"]["workspace_version"] = "internal-version-noise"
    state["workspace_index"]["documents"] = [
        {
            "document_id": "99",
            "title": "Nota clinica",
            "type": "note",
            "status": "draft",
            "source": "user",
            "ai_readable": True,
            "ai_writable": True,
            "version": 3,
            "updated_at": "2026-04-02",
            "is_active": True,
            "is_open": True,
            "has_dirty_draft": False,
            "has_user_edits": True,
            "has_streaming_state": False,
            "hidden_from_agent": False,
            "pinned_for_agent": False,
        },
        {
            "document_id": "12",
            "title": "Contexto del encuentro",
            "type": "context",
            "status": "draft",
            "source": "user",
            "ai_readable": True,
            "ai_writable": True,
            "version": 1,
            "updated_at": "2026-04-02",
            "is_active": False,
            "is_open": True,
            "has_dirty_draft": False,
            "has_streaming_state": False,
            "hidden_from_agent": False,
            "pinned_for_agent": False,
        },
    ]
    state["selected_document_ids"] = ["99", "12"]
    state["available_documents"] = [
        {
            "document_id": "77",
            "title": "Epicrisis",
            "type": "note",
            "status": "final",
            "version": 9,
            "is_active": False,
            "is_open": False,
            "ai_writable": False,
        },
        {
            "document_id": "99",
            "title": "Nota clinica duplicada",
            "type": "note",
            "status": "draft",
            "version": 3,
            "is_active": True,
            "is_open": True,
            "ai_writable": True,
        },
    ]
    state["document_summaries"] = {
        "99": {
            "title": "Nota clinica",
            "type": "note",
            "version": 3,
        },
        "77": {
            "title": "Epicrisis",
            "type": "note",
            "version": 9,
        }
    }
    state["read_documents"] = [
        {
            "document_id": "99",
            "title": "Nota clinica",
            "type": "note",
            "mode": "full",
            "content": "Paciente estable.",
        }
    ]
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
    state["search_results"] = [
        {
            "query": "abdomen",
            "matches": [
                {
                    "document_id": "77",
                    "title": "Epicrisis",
                    "score": 0.8,
                    "snippet": "Coincidencia relevante.",
                }
            ],
        }
    ]

    rendered = render_turn_context(state)

    assert "<copilot_turn_context>" in rendered
    assert "<workspace_index>" in rendered
    assert "internal-version-noise" not in rendered
    assert "<encounter_id>" not in rendered
    assert "<workspace_version>" not in rendered
    assert "<workspace_documents>" in rendered
    assert "<title>Nota clinica</title>" in rendered
    assert "<has_user_edits>True</has_user_edits>" in rendered
    assert "<doctype>context</doctype>" in rendered
    assert "<available_documents>" in rendered
    assert "<title>Epicrisis</title>" in rendered
    assert "Nota clinica duplicada" not in rendered
    assert "<document_summaries>" in rendered
    assert "<version>" not in rendered
    assert "<read_documents>" in rendered
    assert "<read_spans>" in rendered
    assert "<context_view>" in rendered
    assert "<confidence>" not in rendered
    assert "<search_results>" in rendered
    assert 'search_result query="abdomen"' in rendered
    assert "<score>" not in rendered
    assert "<patch_history>" in rendered
    assert "<patch_id>" not in rendered
    assert "<budgets>" not in rendered
    assert "<max_patch_operations>" not in rendered


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
                "content": "Alergia a penicilina.",
                "read_mode": "context_view",
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
