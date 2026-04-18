from app.llm.instructions import (
    DOCUMENTS_ARE_DATA_RULE,
    patch_system_instruction,
    planner_system_instruction,
)


def test_planner_instruction_contains_data_not_instructions_policy():
    instruction = planner_system_instruction()

    assert DOCUMENTS_ARE_DATA_RULE in instruction
    assert 'read_document(mode="full")' in instruction
    assert "El documento activo es solo una pista debil" in instruction
    assert "Cada nuevo mensaje del medico define la prioridad actual del turno." in instruction
    assert "No sigas tareas pendientes de turnos anteriores" in instruction
    assert "prefiere `propose_delete_span`" in instruction
    assert "varias herramientas no-write en paralelo" in instruction
    assert "NUNCA mezcles tools de lectura con propose_* en el mismo turno." in instruction


def test_patch_instruction_contains_data_not_instructions_policy():
    instruction = patch_system_instruction(
        requested_tool_name="propose_replace_span"
    )

    assert DOCUMENTS_ARE_DATA_RULE in instruction
    assert "La tool solicitada fue propose_replace_span." in instruction
    assert "exactText + prefixText + suffixText" in instruction
    assert "incluye los saltos de linea y espacios necesarios" in instruction
    assert "Si el contexto es ambiguo o insuficiente, no inventes contenido clinico." in instruction
    assert "Para replace_span y rewrite_document, debes incluir replacement_text" in instruction
    assert "Para insert_before e insert_after_span, debes incluir inserted_text" in instruction
