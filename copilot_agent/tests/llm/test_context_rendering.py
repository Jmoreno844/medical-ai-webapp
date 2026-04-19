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
            "structure_mode": "structured",
            "sections": [
                {
                    "section_id": "enfermedad_actual",
                    "label": "Enfermedad actual",
                    "heading": "Enfermedad actual",
                    "resolution_source": "literal_heading",
                }
            ],
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
    state["run_memory_notes"] = [
        {
            "source": "last_tool_error",
            "message": "El anchor anterior fue ambiguo.",
        }
    ]
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
    assert "<structure_mode>structured</structure_mode>" in rendered
    assert "<document_sections>" in rendered
    assert "<section_id>enfermedad_actual</section_id>" in rendered
    assert "<read_spans>" in rendered
    assert "<context_view>" in rendered
    assert "<confidence>" not in rendered
    assert "<search_results>" in rendered
    assert 'search_result query="abdomen"' in rendered
    assert "<score>" not in rendered
    assert "<patch_history>" in rendered
    assert "<patch_id>" not in rendered
    assert "<run_memory_notes>" in rendered
    assert "El anchor anterior fue ambiguo." in rendered
    assert "<budgets>" not in rendered
    assert "<max_patch_operations>" not in rendered


def test_render_patch_input_keeps_target_span_and_supporting_context():
    rendered = render_patch_input(
        state={
            **build_state("agrega el antecedente relevante"),
            "read_documents": [
                {
                    "document_id": "99",
                    "title": "Nota clinica",
                    "type": "note",
                    "mode": "full",
                    "content": "Paciente estable.",
                    "structure_mode": "structured",
                    "sections": [
                        {
                            "section_id": "enfermedad_actual",
                            "label": "Enfermedad actual",
                            "heading": "Enfermedad actual",
                            "start_offset": 0,
                            "end_offset": 120,
                            "resolution_source": "literal_heading",
                            "content_preview": "Paciente estable.",
                        },
                        {
                            "section_id": "analisis_clinico",
                            "label": "Analisis clinico",
                            "heading": "Analisis clinico",
                            "start_offset": 121,
                            "end_offset": 240,
                            "resolution_source": "literal_heading",
                            "content_preview": "Analisis estable.",
                        },
                    ],
                }
            ],
            "clinical_plan": {
                "edit_scope": "propagation",
                "clinical_impact_level": "factual",
                "affected_sections": ["enfermedad_actual", "analisis_clinico"],
                "needs_full_note": True,
                "factual_replacements": [
                    {
                        "replacement_id": "edad_paciente",
                        "find_text": "45 años",
                        "replace_text": "46 años",
                        "scope_sections": ["enfermedad_actual", "analisis_clinico"],
                    }
                ],
            },
        },
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
    assert "<target_document_sections>" in rendered
    assert "<available_document_sections>enfermedad_actual, analisis_clinico</available_document_sections>" in rendered
    assert "<supporting_context>" in rendered
    assert "Alergia a penicilina." in rendered
    assert "<edit_plan>" in rendered
    assert "<factual_replacements>" in rendered
    assert "<replacement_id>edad_paciente</replacement_id>" in rendered
    assert "<find_text>45 años</find_text>" in rendered
    assert "<replace_text>46 años</replace_text>" in rendered
