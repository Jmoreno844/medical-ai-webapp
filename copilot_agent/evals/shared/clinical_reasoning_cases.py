from __future__ import annotations

import os
from dataclasses import dataclass
from textwrap import dedent
from typing import Any
from xml.sax.saxutils import escape

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


@dataclass(frozen=True, slots=True)
class ClinicalReasoningCase:
    slug: str
    level: str
    title: str
    doctor_message: str
    document_content: str
    what_it_tests: tuple[str, ...]
    target_document_id: str = "49"
    target_document_title: str = "Historia Clinica"
    target_document_type: str = "note"
    selected_document_ids: tuple[str, ...] = ("49",)


BASE_HEART_FAILURE_NOTE = dedent(
    """
    HISTORIA CLINICA DE CONSULTA EXTERNA

    1. Datos basicos
    Tipo de consulta: Primera vez
    Modalidad: Presencial
    Nombre del paciente: Carlos
    Sexo: Masculino
    Fuente de informacion: Paciente
    Confiabilidad de la informacion: Alta

    2. Motivo de consulta
    "Agitacion y disnea, con ahogamiento nocturno, tos con expectoracion blanquecina y edema en tobillos."

    3. Enfermedad actual
    Tiempo de evolucion: 4 dias
    Inicio: Subito (empeoramiento agudo de sintomas)
    Descripcion cronologica del problema: Paciente refiere que desde hace 4 dias inicia con sensacion de agitacion y falta de aire al caminar dentro de casa. Se asocia a tos con escasa expectoracion blanquecina y sensacion de calor intermitente (sin cuantificar fiebre). Presenta presion o pesadez toracica, principalmente al agitarse. La disnea empeora al acostarse, refiriendo ahogamiento que impidio el sueno anoche. Ha notado hinchazon progresiva en ambos tobillos, con los zapatos que le quedan mas apretados y mayor facilidad para cansarse. Niega silbidos, flema amarilla, hemoptisis o sincope.
    Sintomas principales: Disnea, tos, edema de miembros inferiores, presion toracica.
    Localizacion: Torax, miembros inferiores.
    Intensidad: Disnea severa ("muy agitado", "casi no pude dormir"), tos con "poquita flema", presion toracica "no fuerte, mas como una presion o pesadez", edema ++/++++.
    Factores desencadenantes: Disnea y presion toracica con el esfuerzo, disnea al decubito.
    Factores atenuantes: Disnea mejora al sentarse.
    Sintomas asociados: Tos con expectoracion blanquecina, sensacion de calor, fatiga facil.
    Evolucion hasta hoy: Progresiva exacerbacion de la disnea y edema, culminando en dificultad para dormir anoche.
    Impacto funcional: Limitacion para actividades basicas como caminar dentro de casa, imposibilidad para el decubito, fatiga.

    4. Revision por sistemas
    General: Fatiga facil, sensacion de calor intermitente.
    Cardiovascular: Presion toracica inespecifica al esfuerzo, disnea de esfuerzo y de decubito, edema de miembros inferiores.
    Respiratorio: Disnea, tos con expectoracion blanquecina. Niega silbidos, flema amarilla, hemoptisis.
    Neurologico: Niega desmayos.
    Piel y faneras: Edema en tobillos.
    Endocrino: Antecedente de Diabetes Mellitus.

    5. Antecedentes
    Personales patologicos
    HTA: Si
    DM: Si
    Otros: Enfermedad cardiaca previa ("corazon un poco debil" hace anos, nombre no recordado por el paciente, sugestivo de Insuficiencia Cardiaca).
    Farmacologicos
    Medicamentos actuales: Losartan, Carvedilol, Metformina, Furosemida.
    Toxicos / habitos
    Tabaco: Ex-fumador (fumo muchos anos).
    Sueno: Alterado por disnea.

    6. Signos vitales
    TA: 148/86 mmHg
    FC: 106 lpm
    FR: 24 rpm
    Temperatura: 37.8 C
    Saturacion O2: 90% al aire ambiente

    7. Examen fisico
    General
    Estado general: Alerta, habla en frases completas, sin cianosis.
    Cardiopulmonar
    Cardiaco: Ruidos cardiacos ritmicos, taquicardicos.
    Pulmonar: Crepitos bibasales, mas marcados en base derecha, sin sibilancias claras.
    Abdomen
    No dolor abdominal.
    Extremidades
    Edema en ambos tobillos, ++/++++.
    Neurologico
    No focalizacion neurologica evidente.
    Hallazgos relevantes dirigidos
    Taquicardia, taquipnea, febricula, hipoxemia al aire ambiente. Crepitos bibasales. Edema bilateral de miembros inferiores.

    8. Impresion diagnostica / Problemas
    Descompensacion de Insuficiencia Cardiaca Cronica (probable, pendiente de estudios).
    Infeccion respiratoria aguda (posible factor precipitante o coexistente).
    Hipertension Arterial Sistemica (no controlada en el contexto agudo).
    Diabetes Mellitus tipo 2.

    9. Analisis clinico
    Resumen interpretativo del caso: Paciente masculino, con antecedentes de HTA, DM y probable insuficiencia cardiaca, ex-fumador, quien consulta por cuadro agudo de disnea progresiva de 4 dias de evolucion, que se exacerba con el esfuerzo y en decubito, asociada a tos con expectoracion blanquecina, sensacion de calor y edema de miembros inferiores. Al examen fisico presenta taquicardia, taquipnea, febricula e hipoxemia significativa al aire ambiente. Se auscultan crepitos bibasales y se evidencia edema en tobillos.
    Diagnosticos diferenciales: Insuficiencia cardiaca aguda descompensada (edema agudo de pulmon cardiogenico), Neumonia, Exacerbacion de enfermedad pulmonar obstructiva cronica (aunque no diagnosticada, por antecedente de tabaquismo).
    Signos de alarma presentes o ausentes:
    Presentes: Disnea de reposo/decubito, taquipnea (FR 24), taquicardia (FC 106), hipoxemia (SpO2 90%), crepitos bibasales, edema de miembros inferiores, febricula.
    Ausentes: Hemoptisis, cianosis evidente, sincope.
    Justificacion diagnostica: La combinacion de disnea progresiva, ortopnea, edema bilateral de miembros inferiores, crepitos bibasales, taquicardia e hipoxemia, en un paciente con multiples factores de riesgo cardiovascular y antecedente de "corazon debil", es altamente sugestiva de una descompensacion de insuficiencia cardiaca. La tos y febricula pueden indicar un factor precipitante infeccioso, lo cual requerira correlacion con estudios.

    10. Plan de manejo
    Diagnostico / estudios
    Se solicitaran estudios para orientar el diagnostico diferencial.
    Seguimiento
    Signos de alarma explicados: Si.
    """
).strip()


_CASES: tuple[ClinicalReasoningCase, ...] = (
    ClinicalReasoningCase(
        slug="heart-failure-diuretic-nonadherence",
        level="medio",
        title="Suspension de furosemida + ortopnea progresiva",
        doctor_message=(
            "Ojo que acabo de confirmar con la esposa que el dejo de tomar la furosemida hace como una semana porque se le acabo, "
            "lleva varios dias durmiendo con tres almohadas y en el ultimo mes ha subido como cuatro kilos. Dejame la nota bien actualizada con eso."
        ),
        document_content=BASE_HEART_FAILURE_NOTE,
        what_it_tests=(
            "si agrega los nuevos hechos sin romper la cronologia",
            "si reinterpreta mejor la disnea, ortopnea y edema",
            "si ajusta impresion y plan sin volverse excesivo",
        ),
    ),
    ClinicalReasoningCase(
        slug="post-knee-replacement-pe-signal",
        level="dificil",
        title="Reemplazo de rodilla reciente + pantorrilla asimetrica",
        doctor_message=(
            "Esperate, la hija me acaba de decir que hace 12 dias le hicieron reemplazo de rodilla izquierda y desde ayer esa pantorrilla esta mas hinchada y dolorosa que la otra. "
            "Revisame la nota con eso porque ya no me suena igual el cuadro."
        ),
        document_content=BASE_HEART_FAILURE_NOTE,
        what_it_tests=(
            "si detecta que aparece un factor fuerte para TVP o TEP",
            "si no deja la nota anclada solo en neumonia o falla cardiaca",
            "si cambia el nivel de alerta y el analisis clinico",
        ),
    ),
    ClinicalReasoningCase(
        slug="bnp-gasometry-cxr-heart-failure-objective-data",
        level="muy_dificil",
        title="Radiografia, BNP y gasometria orientan edema pulmonar cardiogenico",
        doctor_message=(
            "Ya salieron los estudios: la radiografia reporta edema intersticial bilateral y pequeno derrame pleural derecho, sin consolidacion focal; "
            "el BNP esta en 1850; la gasometria al aire ambiente muestra pH 7.47, pCO2 31 y pO2 58. Dejame la nota aterrizada con esto y sin simplificar de mas lo que esta pasando."
        ),
        document_content=BASE_HEART_FAILURE_NOTE,
        what_it_tests=(
            "si integra datos objetivos y no se casa con una sola narrativa facil",
            "si sube el peso diagnostico de falla cardiaca descompensada",
            "si mantiene diferenciales razonables sin simplificar en exceso",
        ),
    ),
)


def all_clinical_reasoning_cases() -> tuple[ClinicalReasoningCase, ...]:
    raw_exact = str(os.getenv("REASONING_CASE_EXACT") or "").strip()
    if raw_exact:
        try:
            exact_index = int(raw_exact)
        except ValueError:
            return _CASES
        if 1 <= exact_index <= len(_CASES):
            return (_CASES[exact_index - 1],)
        return _CASES

    raw_limit = str(os.getenv("REASONING_CASE_LIMIT") or "").strip()
    if not raw_limit:
        return _CASES
    try:
        limit = int(raw_limit)
    except ValueError:
        return _CASES
    if limit <= 0:
        return _CASES
    return _CASES[:limit]


_READ_DOC_TOOL_CALL_ID = "tc_read_doc_eval_history"


def _shorten_for_tool(value: Any, *, max_length: int = 12000) -> str:
    if value is None:
        return ""
    text = " ".join(str(value).split())
    return text[:max_length]


def _render_read_document_observation(case: "ClinicalReasoningCase") -> str:
    """XML tool observation matching the real runtime format for read_document(mode='full')."""
    summary = f"Documento {case.target_document_id} leido en modo full"
    excerpt = _shorten_for_tool(case.document_content)
    return "\n".join([
        '<tool_observation name="read_document" status="success">',
        f"  <summary>{escape(summary)}</summary>",
        f"  <document_id>{escape(case.target_document_id)}</document_id>",
        f"  <title>{escape(case.target_document_title)}</title>",
        "  <mode>full</mode>",
        f"  <excerpt>{escape(excerpt)}</excerpt>",
        "</tool_observation>",
    ])


def build_reasoning_conv_history(case: "ClinicalReasoningCase") -> list:
    """LangGraph conversation history at the point after the document has already been read.

    Sequence injected into invoke_model messages:
      1. HumanMessage  — doctor's message with new clinical information
      2. AIMessage     — simulated LLM tool call: read_document(document_id, mode='full')
      3. ToolMessage   — full document content as the tool observation XML

    The planner must demonstrate clinical reasoning (set_edit_plan → propose patches)
    without needing to read the document again.
    """
    return [
        HumanMessage(content=case.doctor_message),
        AIMessage(
            content="Voy a leer el documento completo para poder actualizar la nota.",
            tool_calls=[
                {
                    "name": "read_document",
                    "args": {
                        "document_id": case.target_document_id,
                        "mode": "full",
                    },
                    "id": _READ_DOC_TOOL_CALL_ID,
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(
            content=_render_read_document_observation(case),
            tool_call_id=_READ_DOC_TOOL_CALL_ID,
            name="read_document",
        ),
    ]


def build_reasoning_target_document(case: "ClinicalReasoningCase") -> dict[str, Any]:
    return {
        "document_id": case.target_document_id,
        "title": case.target_document_title,
        "type": case.target_document_type,
        "version": 1,
        "status": "active",
        "is_active": True,
        "is_open": True,
        "ai_writable": True,
        "short_summary": case.title,
    }


def build_reasoning_eval_state(case: "ClinicalReasoningCase") -> dict[str, Any]:
    """Minimal workspace state for the clinical reasoning eval.

    The state intentionally has NO pre-filled document reads.  Document content
    reaches the planner exclusively through the conversation history returned by
    build_reasoning_conv_history(), which simulates the real LangGraph turn where
    the LLM called read_document and received the full note as a ToolMessage.
    """
    target_document = build_reasoning_target_document(case)
    return {
        "tenant_id": "doctor:reasoning-eval",
        "user_id": "doctor:reasoning-eval",
        "encounter_id": "reasoning-eval-encounter",
        "active_document_id": case.target_document_id,
        "thread_id": f"copilot:reasoning:{case.slug}",
        "user_message": case.doctor_message,
        "workspace_index": {
            "encounter_id": "reasoning-eval-encounter",
            "workspace_version": "reasoning-v1",
            "active_document_id": case.target_document_id,
            "open_document_ids": list(case.selected_document_ids),
            # Only document metadata visible here — content comes through ToolMessage.
            "documents": [target_document],
        },
        # Messages are passed explicitly to invoke_model via build_reasoning_conv_history.
        "messages": [],
        "selected_document_ids": list(case.selected_document_ids),
        "available_documents": [target_document],
        "context_view": None,
        "document_summaries": {
            case.target_document_id: {
                "title": case.target_document_title,
                "type": case.target_document_type,
                "version": 1,
                "short_summary": case.title,
            }
        },
        # No pre-filled reads — document content only lives in the ToolMessage history.
        "document_reads": [],
        "read_spans": [],
        "retrieved_context": [],
        "read_documents": [],
        "search_matches": [],
        "search_query": None,
        "search_results": [],
        "patch_history": {},
        "tool_calls": [],
        "tool_results": [],
        "planner_decisions": [],
        "current_plan_step": "start",
        "iteration_count": 0,
        "max_iterations": 6,
        "max_document_reads": 4,
        "patch_operations_count": 0,
        "max_patch_operations": 8,
        "planner_retry_count": 0,
        "last_planner_error": None,
        "last_tool_error": None,
        "target_document_id": case.target_document_id,
        "target_document_title": case.target_document_title,
        "target_selection_reason": "reasoning_eval_full_note_context",
        "base_version": 1,
        "patch_set_preview": None,
        "patch_preview": None,
        "patch_id": None,
        "final_response": None,
        "requires_human_review": False,
        "review_result": None,
        "review_comment": None,
        "run_error": None,
        "trace_metadata": {"reasoning_case": case.slug},
        "clinical_plan": None,
    }
