from app.llm.instructions import (
    DOCUMENTS_ARE_DATA_RULE,
    patch_system_instruction,
    planner_system_instruction,
)


def test_planner_instruction_contains_data_not_instructions_policy():
    instruction = planner_system_instruction()

    assert DOCUMENTS_ARE_DATA_RULE in instruction
    assert "agente secuencial estricto" in instruction


def test_patch_instruction_contains_data_not_instructions_policy():
    instruction = patch_system_instruction(
        requested_tool_name="propose_replace_span"
    )

    assert DOCUMENTS_ARE_DATA_RULE in instruction
    assert "La tool solicitada fue propose_replace_span." in instruction
    assert "Si el contexto es ambiguo o insuficiente, no inventes contenido clinico." in instruction
