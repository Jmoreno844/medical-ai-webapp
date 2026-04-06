from __future__ import annotations

import os
from dataclasses import dataclass
from textwrap import dedent
from typing import Any, Literal

from langchain_core.messages import HumanMessage


EditScope = Literal["propagation", "reinterpretation"]
ImpactLevel = Literal["factual", "clinical"]


@dataclass(frozen=True, slots=True)
class LiveClinicalCase:
    slug: str
    summary: str
    user_message: str
    target_document_id: str
    target_document_title: str
    target_document_type: str
    target_document_content: str
    supporting_context: tuple[dict[str, Any], ...]
    affected_sections: tuple[str, ...]
    edit_scope: EditScope
    clinical_impact_level: ImpactLevel
    selected_document_ids: tuple[str, ...] = ()
    workspace_documents: tuple[dict[str, Any], ...] = ()


# The matrix intentionally mixes pure propagation and real reinterpretation.
# That keeps evals close to the doctor workflow: some requests only require the
# same fact to appear consistently, while others force the planner/drafter to
# re-state risk, diagnosis, and plan after a new clinically meaningful fact.
_CASES: tuple[LiveClinicalCase, ...] = (
    LiveClinicalCase(
        slug="cystitis-pregnancy-allergy-reinterpretation",
        summary="Reinterpretar una historia clinica de cistitis cuando aparece embarazo positivo y anafilaxia a penicilina.",
        user_message=(
            "Con los documentos ya seleccionados, actualiza la Historia Clinica: la beta hCG de hoy es positiva "
            "y hay antecedente documentado de anafilaxia a penicilina. Reinterpreta antecedentes relevantes, "
            "enfermedad actual, impresion diagnostica, analisis clinico y plan. Elimina cualquier frase que diga "
            "que niega embarazo o alergias medicamentosas, y evita recomendar penicilinas."
        ),
        target_document_id="43",
        target_document_title="Historia Clinica",
        target_document_type="note",
        target_document_content=dedent(
            """
            # HISTORIA CLINICA DE CONSULTA EXTERNA

            ## 1. Datos basicos

            - Tipo de consulta: Primera vez
            - Edad: 29 anos
            - Sexo: Femenino

            ## 2. Motivo de consulta

            - "Dolor al orinar y aumento en la frecuencia urinaria desde hace 3 dias."

            ## 3. Enfermedad actual

            - Tiempo de evolucion: 3 dias
            - Descripcion cronologica del problema: Paciente refiere inicio hace 3 dias de dolor al orinar y aumento en la frecuencia urinaria. Adicionalmente, presenta ardor al final de la miccion, sensacion de vaciamiento incompleto y urgencia urinaria.
            - Sintomas asociados: Niega fiebre, escalofrios, dolor lumbar, nauseas o vomito. Niega flujo vaginal, mal olor o prurito vaginal.
            - Evolucion hasta hoy: Los sintomas persisten desde el inicio, motivando la consulta.

            ## 4. Revision por sistemas

            - General: Niega fiebre, escalofrios, nauseas, vomito.
            - Genitourinario: Disuria, polaquiuria, ardor al final de la miccion, sensacion de vaciamiento incompleto, urgencia urinaria. Niega dolor lumbar. Niega flujo vaginal, mal olor o prurito vaginal. Ultima menstruacion hace 2 semanas, niega embarazo.

            ## 5. Antecedentes

            ### Personales patologicos

            - Otros: Episodios previos de infeccion del tracto urinario, el ultimo hace aproximadamente 1 ano.

            ### Farmacologicos

            - Medicamentos actuales: Niega toma de medicamentos de base.

            ### Alergicos

            - Medicamentos: Niega alergias medicamentosas conocidas.

            ## 8. Impresion diagnostica / Problemas

            1. Cistitis aguda no complicada.

            ## 9. Analisis clinico

            - Resumen interpretativo del caso: Paciente femenina de 29 anos, con sintomas urinarios bajos de 3 dias de evolucion. Niega sintomas sistemicos o de pielonefritis. Antecedente de ITU previa.
            - Justificacion diagnostica: Cuadro clinico tipico de cistitis aguda no complicada en paciente joven, sin factores de riesgo de complicacion ni signos de alarma.

            ## 10. Plan de manejo

            ### Diagnostico / estudios

            - Laboratorios: Parcial de orina y urocultivo si no hay mejoria o en caso de recurrencia.

            ### Tratamiento

            - Farmacologico: Antibiotico segun guia local para cistitis no complicada.
            - No farmacologico: Hidratacion adecuada.

            ### Seguimiento

            - Signos de alarma explicados: Fiebre, dolor lumbar, vomito o empeoramiento de los sintomas.
            """
        ).strip(),
        supporting_context=(
            {
                "document_id": "31",
                "title": "Laboratorio urgencias",
                "type": "lab_result",
                "read_mode": "supporting_context",
                "excerpt": (
                    "Beta hCG cuantitativa positiva en urgencias. Embarazo temprano confirmado el mismo dia de la consulta."
                ),
            },
            {
                "document_id": "32",
                "title": "Antecedente alergico previo",
                "type": "encounter_fact",
                "read_mode": "supporting_context",
                "excerpt": (
                    "Evento documentado de anafilaxia a penicilina en 2024 con urticaria generalizada, broncoespasmo e hipotension."
                ),
            },
        ),
        affected_sections=(
            "antecedentes_relevantes",
            "enfermedad_actual",
            "impresion_diagnostica",
            "analisis_clinico",
            "plan",
        ),
        edit_scope="reinterpretation",
        clinical_impact_level="clinical",
        selected_document_ids=("31", "32", "43"),
        workspace_documents=(
            {
                "document_id": "31",
                "title": "Laboratorio urgencias",
                "type": "lab_result",
                "version": 1,
                "status": "active",
                "is_active": True,
                "is_open": True,
                "ai_writable": False,
                "short_summary": "Beta hCG positiva del dia de la consulta.",
            },
            {
                "document_id": "32",
                "title": "Antecedente alergico previo",
                "type": "encounter_fact",
                "version": 1,
                "status": "active",
                "is_active": True,
                "is_open": True,
                "ai_writable": False,
                "short_summary": "Anafilaxia a penicilina documentada previamente.",
            },
            {
                "document_id": "43",
                "title": "Historia Clinica",
                "type": "note",
                "version": 1,
                "status": "active",
                "is_active": True,
                "is_open": True,
                "ai_writable": True,
                "short_summary": "Historia clinica ambulatoria de sintomas urinarios bajos.",
            },
        ),
    ),
    LiveClinicalCase(
        slug="respiratory-deterioration-reevaluation-reinterpretation",
        summary="Reinterpretar una historia clinica respiratoria cuando la reevaluacion muestra hipoxemia, taquipnea y somnolencia.",
        user_message=(
            "Con los documentos ya seleccionados, actualiza la Historia Clinica para reflejar deterioro respiratorio en la reevaluacion. "
            "En signos vitales reemplaza FC 96 lpm, FR 20 rpm y saturacion O2 94% al ambiente por FC 112 lpm, FR 30 rpm y saturacion O2 89% al aire ambiente. "
            "En examen fisico u hallazgos dirigidos deja constancia de que el paciente esta mas taquipneico, se fatiga al hablar y luce mas somnoliento. "
            "Reinterpreta analisis clinico, impresion diagnostica/problemas y plan de manejo para reflejar mayor gravedad y necesidad de vigilancia estrecha o atencion inmediata, sin inventar tratamientos nuevos no documentados."
        ),
        target_document_id="49",
        target_document_title="Historia Clinica",
        target_document_type="note",
        target_document_content=dedent(
            """
            # HISTORIA CLINICA DE CONSULTA EXTERNA

            ## 1. Datos basicos

            - Fecha: 27 de octubre de 2023
            - Hora: 6:00 pm
            - Tipo de consulta: Primera vez (por esta condicion)
            - Modalidad: Presencial
            - Edad: 67 anos
            - Fuente de informacion: Paciente
            - Confiabilidad de la informacion: Alta

            ## 2. Motivo de consulta

            - "Paciente de 67 anos refiere tos de 5 dias de evolucion, inicialmente seca y ahora con expectoracion amarillenta, fiebre nocturna (max. 38.3C), disnea de esfuerzo leve y dolor toracico pleuritico derecho."

            ## 3. Enfermedad actual

            - Tiempo de evolucion: 5 dias
            - Inicio: Gradual
            - Descripcion cronologica del problema: Paciente refiere inicio hace 5 dias con tos seca, que desde hace 2 dias se torno productiva con expectoracion amarillenta. Ha presentado fiebre predominantemente nocturna, con registro maximo de 38.3C el dia previo a la consulta. Asocia disnea de esfuerzo leve al caminar rapido o subir escaleras, la cual cede en reposo. Tambien refiere dolor toracico en hemitorax derecho, de tipo pleuritico, que se exacerba con la tos y la respiracion profunda. Inicialmente presento odinofagia leve, la cual ya resolvio. Niega rinorrea, nauseas, vomitos, diarrea o sibilancias.
            - Sintomas principales: Tos, expectoracion amarillenta, fiebre, disnea, dolor toracico derecho.
            - Localizacion: Hemitorax derecho (dolor), Pulmonar (sintomas respiratorios).
            - Intensidad: Fiebre 38.3C, disnea leve, dolor "un poco".
            - Factores desencadenantes: Disnea con actividad fisica, dolor con tos/respiracion profunda.
            - Factores atenuantes: Disnea en reposo.
            - Sintomas asociados: Fiebre, odinofagia (inicialmente).
            - Tratamientos usados antes de la consulta: Acetaminofen (por la fiebre).
            - Evolucion hasta hoy: Persistencia de sintomas respiratorios con empeoramiento de la tos a productiva y fiebre intermitente.
            - Impacto funcional: Disnea que limita actividad fisica moderada (caminar rapido/subir escaleras).

            ## 4. Revision por sistemas

            - General: Decaido, refiere fiebre.
            - Cardiovascular: Niega sibilancias o edemas en piernas.
            - Respiratorio: Tos, expectoracion, disnea de esfuerzo, dolor toracico pleuritico derecho.
            - Gastrointestinal: Niega nauseas, vomito o diarrea.
            - Neurologico: Orientado.
            - Musculoesqueletico: Niega dolor o hinchazon en piernas.
            - Piel y faneras: Hidratado.
            - Endocrino: Antecedente de Diabetes Mellitus.

            ## 5. Antecedentes

            ### Personales patologicos

            - HTA: Si (en manejo con losartan)
            - DM: Si (en manejo con metformina)
            - Otros: Niega hospitalizaciones recientes o uso de antibioticos en las ultimas semanas.

            ### Farmacologicos

            - Medicamentos actuales: Losartan, Metformina, Acetaminofen (temporalmente).
            - Automedicacion: Acetaminofen por fiebre.

            ### Alergicos

            - Medicamentos: Niega.

            ### Toxicos / habitos

            - Tabaco: Ex-fumador (dejo hace 8 anos).

            ### Familiares

            - Otros: Nieto con gripa la semana pasada (contacto).

            ## 6. Signos vitales

            - TA: 128/76 mmHg
            - FC: 96 lpm
            - FR: 20 rpm
            - Temperatura: 38.1C
            - Saturacion O2: 94% al ambiente

            ## 7. Examen fisico

            ### General

            - Estado general: Decaido pero orientado.
            - Hidratacion: Hidratado.

            ### Cardiopulmonar

            - Cardiaco: Corazon ritmico.
            - Pulmonar: Sin uso de musculos accesorios. Crepitos en la base derecha. Entrada de aire disminuida en la base derecha. No sibilancias.

            ### Extremidades

            - No hay edema en piernas.

            ### Neurologico

            - Orientado.

            ### Hallazgos relevantes dirigidos

            - Crepitos y disminucion del murmullo vesicular en base pulmonar derecha.
            - Paciente febril (38.1C), taquicardico (96 lpm) y taquipneico (20 rpm), con SaO2 94% al ambiente.

            ## 8. Impresion diagnostica / Problemas

            1. Neumonia Adquirida en la Comunidad (NAC) - Hemitorax derecho.
            2. Hipertension Arterial (HTA) controlada.
            3. Diabetes Mellitus (DM) controlada.
            4. Ex-fumador.

            ## 9. Analisis clinico

            - Resumen interpretativo del caso: Paciente masculino de 67 anos, con comorbilidades (HTA, DM, ex-fumador) y antecedente de contacto con infeccion respiratoria (nieto con gripa), quien presenta un cuadro clinico de 5 dias de evolucion compatible con infeccion respiratoria baja. Los sintomas incluyen tos productiva, fiebre, disnea de esfuerzo y dolor toracico pleuritico. El examen fisico revela hallazgos pulmonares focales (crepitos y disminucion del murmullo vesicular en base derecha) y signos vitales alterados (fiebre, taquicardia, taquipnea, desaturacion leve), los cuales son altamente sugestivos de una Neumonia Adquirida en la Comunidad.
            - Diagnosticos diferenciales: Bronquitis aguda, Exacerbacion de EPOC (dado antecedente de tabaquismo), Embolia Pulmonar (aunque menos probable sin otros factores de riesgo especificos y con clara evidencia infecciosa).
            - Signos de alarma presentes o ausentes: Presentes (edad >65 anos, comorbilidades HTA y DM, SaO2 94%, FR 20 rpm, FC 96 lpm). Ausentes signos de inestabilidad hemodinamica o alteracion neurologica severa.
            - Justificacion diagnostica: La combinacion de sintomatologia respiratoria aguda (tos, fiebre, expectoracion, disnea, dolor pleuritico) con signos fisicos de consolidacion pulmonar en un paciente con factores de riesgo epidemiologicos y de huesped es altamente consistente con el diagnostico de Neumonia Adquirida en la Comunidad.

            ## 10. Plan de manejo

            ### Educacion

            - Se explican signos de alarma para consultar de inmediato: si se ahoga mas, se pone confuso, no tolera liquidos o la fiebre empeora.

            ### Seguimiento

            - Signos de alarma explicados: Si se ahoga mas, se pone confuso, no tolera liquidos o la fiebre empeora, consultar de inmediato.

            ## 11. Cierre

            - Paciente comprende indicaciones: Si
            - Se resuelven dudas: Si
            """
        ).strip(),
        supporting_context=(
            {
                "document_id": "45",
                "title": "Reevaluacion enfermeria",
                "type": "encounter_fact",
                "read_mode": "supporting_context",
                "excerpt": (
                    "Reevaluacion posterior: frecuencia cardiaca 112 lpm, frecuencia respiratoria 30 rpm y saturacion 89% al aire ambiente."
                ),
            },
            {
                "document_id": "46",
                "title": "Observacion medica breve",
                "type": "encounter_fact",
                "read_mode": "supporting_context",
                "excerpt": (
                    "Paciente mas taquipneico, con fatiga al hablar y aspecto mas somnoliento que en la valoracion inicial."
                ),
            },
        ),
        affected_sections=(
            "signos_vitales",
            "examen_fisico",
            "analisis_clinico",
            "impresion_diagnostica_problemas",
            "plan_de_manejo",
        ),
        edit_scope="reinterpretation",
        clinical_impact_level="clinical",
        selected_document_ids=("45", "46", "49"),
        workspace_documents=(
            {
                "document_id": "45",
                "title": "Reevaluacion enfermeria",
                "type": "encounter_fact",
                "version": 1,
                "status": "active",
                "is_active": True,
                "is_open": True,
                "ai_writable": False,
                "short_summary": "Signos vitales de reevaluacion con hipoxemia y taquipnea.",
            },
            {
                "document_id": "46",
                "title": "Observacion medica breve",
                "type": "encounter_fact",
                "version": 1,
                "status": "active",
                "is_active": True,
                "is_open": True,
                "ai_writable": False,
                "short_summary": "Reevaluacion con mayor fatiga al hablar y somnolencia.",
            },
            {
                "document_id": "49",
                "title": "Historia Clinica",
                "type": "note",
                "version": 1,
                "status": "active",
                "is_active": True,
                "is_open": True,
                "ai_writable": True,
                "short_summary": "Historia clinica respiratoria con reevaluacion pendiente de reinterpretacion.",
            },
        ),
    ),
    LiveClinicalCase(
        slug="anticoagulation-hold-before-biopsy",
        summary="Suspender anticoagulacion antes de biopsia programada y propagar el cambio.",
        user_message=(
            "Se programo biopsia renal para el viernes y nefrologia indico suspender apixaban 48 horas antes. "
            "Actualiza enfermedad actual, antecedentes relevantes, analisis clinico y plan. "
            "Quita cualquier instruccion que diga continuar anticoagulacion sin cambios."
        ),
        target_document_id="99",
        target_document_title="Nota clinica nefrologia",
        target_document_type="note",
        target_document_content=dedent(
            """
            ANTECEDENTES RELEVANTES:
            - Fibrilacion auricular no valvular en apixaban 5 mg cada 12 horas.
            - ERC estadio 3.

            ENFERMEDAD ACTUAL:
            Paciente en estudio por proteinuria. Se planteo biopsia renal, pendiente fecha definitiva. Hasta ahora se mantiene apixaban sin modificaciones.

            ANALISIS CLINICO:
            Riesgo tromboembolico conocido, pero sin procedimiento invasivo inmediato documentado.

            PLAN:
            Continuar apixaban sin cambios. Pendiente confirmar cronograma de biopsia y reevaluar en control.
            """
        ).strip(),
        supporting_context=(
            {
                "document_id": "ctx-biopsy-1",
                "title": "Interconsulta nefrologia",
                "type": "care_plan",
                "read_mode": "supporting_context",
                "excerpt": (
                    "Biopsia renal programada para 2026-04-10. Suspender apixaban 48 horas antes y reiniciar segun hemostasia post procedimiento."
                ),
            },
        ),
        affected_sections=(
            "antecedentes_relevantes",
            "enfermedad_actual",
            "analisis_clinico",
            "plan",
        ),
        edit_scope="reinterpretation",
        clinical_impact_level="clinical",
    ),
    LiveClinicalCase(
        slug="postpartum-fever-sepsis-reinterpretation",
        summary="Reinterpretar fiebre puerperal como cuadro infeccioso y reforzar conducta.",
        user_message=(
            "Ahora hay fiebre de 39.1 C, taquicardia y loquios fetidos en puerpera de 3 dias. "
            "Actualiza enfermedad actual, impresion diagnostica, analisis clinico y plan. "
            "Elimina cualquier texto que la describa como evolucion estable sin datos de infeccion."
        ),
        target_document_id="99",
        target_document_title="Nota clinica puerperio",
        target_document_type="note",
        target_document_content=dedent(
            """
            ENFERMEDAD ACTUAL:
            Puerpera de 3 dias posparto vaginal con dolor hipogastrico leve. Afebril al momento del examen previo y tolerando via oral.

            IMPRESION DIAGNOSTICA:
            Evolucion puerperal esperada sin signos de alarma.

            ANALISIS CLINICO:
            Cuadro estable, sin evidencia actual de infeccion o sangrado significativo.

            PLAN:
            Manejo analgesico simple, hidratacion y control ambulatorio en 72 horas.
            """
        ).strip(),
        supporting_context=(
            {
                "document_id": "ctx-postpartum-1",
                "title": "Hoja de observacion",
                "type": "encounter_fact",
                "read_mode": "supporting_context",
                "excerpt": (
                    "Ultimos signos vitales: T 39.1 C, FC 122 lpm. Refiere loquios fetidos y dolor uterino a la palpacion."
                ),
            },
        ),
        affected_sections=(
            "enfermedad_actual",
            "impresion_diagnostica",
            "analisis_clinico",
            "plan",
        ),
        edit_scope="reinterpretation",
        clinical_impact_level="clinical",
    ),
    LiveClinicalCase(
        slug="chronic-kidney-disease-stage-propagation",
        summary="Propagar estadio de ERC confirmado a la nota de seguimiento.",
        user_message=(
            "Laboratorio y nefrologia confirman ERC estadio 4. Actualiza antecedentes relevantes, enfermedad actual, analisis clinico y plan, "
            "y corrige cualquier referencia previa a ERC estadio 2."
        ),
        target_document_id="99",
        target_document_title="Nota clinica medicina interna",
        target_document_type="note",
        target_document_content=dedent(
            """
            ANTECEDENTES RELEVANTES:
            - Hipertension arterial.
            - ERC estadio 2 segun registros previos.

            ENFERMEDAD ACTUAL:
            Paciente consulta por edema maleolar y astenia. Se mantiene seguimiento por funcion renal alterada leve.

            ANALISIS CLINICO:
            Deterioro renal cronico leve, sin criterios actuales de progresion avanzada.

            PLAN:
            Continuar manejo habitual y solicitar control de creatinina en consulta externa.
            """
        ).strip(),
        supporting_context=(
            {
                "document_id": "ctx-ckd-1",
                "title": "Nota nefrologia",
                "type": "specialist_note",
                "read_mode": "supporting_context",
                "excerpt": (
                    "TFGe estimada 24 ml/min/1.73 m2, compatible con ERC estadio 4. Se recomienda ajustar seguimiento y medicacion a enfermedad renal avanzada."
                ),
            },
        ),
        affected_sections=(
            "antecedentes_relevantes",
            "enfermedad_actual",
            "analisis_clinico",
            "plan",
        ),
        edit_scope="propagation",
        clinical_impact_level="factual",
    ),
    LiveClinicalCase(
        slug="hyperkalemia-losartan-hold-reinterpretation",
        summary="Reinterpretar el plan por hiperpotasemia documentada con suspension de losartan.",
        user_message=(
            "El potasio regreso en 6.1 mmol/L y se indico suspender losartan. "
            "Actualiza enfermedad actual, impresion diagnostica, analisis clinico y plan, y quita cualquier recomendacion de continuar el ARB."
        ),
        target_document_id="99",
        target_document_title="Nota clinica hipertension",
        target_document_type="note",
        target_document_content=dedent(
            """
            ENFERMEDAD ACTUAL:
            Paciente con hipertension y nefropatia diabetica en control. Hasta el momento tolera losartan sin efectos adversos referidos.

            IMPRESION DIAGNOSTICA:
            Hipertension arterial controlada con buen apego terapeutico.

            ANALISIS CLINICO:
            Sin alteraciones recientes de laboratorio que obliguen a modificar el esquema antihipertensivo.

            PLAN:
            Continuar losartan 50 mg cada 12 horas y control ambulatorio en 1 mes.
            """
        ).strip(),
        supporting_context=(
            {
                "document_id": "ctx-k-1",
                "title": "Resultado laboratorio",
                "type": "lab_result",
                "read_mode": "supporting_context",
                "excerpt": "Potasio serico 6.1 mmol/L. Se notifica al equipo tratante; se recomienda suspender losartan y repetir electrolitos hoy.",
            },
        ),
        affected_sections=(
            "enfermedad_actual",
            "impresion_diagnostica",
            "analisis_clinico",
            "plan",
        ),
        edit_scope="reinterpretation",
        clinical_impact_level="clinical",
    ),
    LiveClinicalCase(
        slug="positive-pregnancy-test-teratogen-stop",
        summary="Reinterpretar tratamiento por prueba de embarazo positiva mientras usaba enalapril.",
        user_message=(
            "La beta hCG es positiva y la paciente estaba tomando enalapril. "
            "Actualiza antecedentes relevantes, enfermedad actual, analisis clinico y plan. "
            "Quita cualquier indicacion de continuar enalapril y documenta la implicacion del embarazo confirmado."
        ),
        target_document_id="99",
        target_document_title="Nota clinica hipertension en mujer en edad fertil",
        target_document_type="note",
        target_document_content=dedent(
            """
            ANTECEDENTES RELEVANTES:
            - Hipertension arterial esencial.
            - Niega embarazo actual.

            ENFERMEDAD ACTUAL:
            Consulta por mareo leve. Usa enalapril 10 mg cada 12 horas con buen control tensional.

            ANALISIS CLINICO:
            Control adecuado de hipertension sin cambios recientes de contexto clinico.

            PLAN:
            Continuar enalapril y control en 4 semanas.
            """
        ).strip(),
        supporting_context=(
            {
                "document_id": "ctx-preg-1",
                "title": "Laboratorio urgencias",
                "type": "lab_result",
                "read_mode": "supporting_context",
                "excerpt": "Beta hCG cuantitativa positiva. Embarazo temprano confirmado en urgencias.",
            },
        ),
        affected_sections=(
            "antecedentes_relevantes",
            "enfermedad_actual",
            "analisis_clinico",
            "plan",
        ),
        edit_scope="reinterpretation",
        clinical_impact_level="clinical",
    ),
    LiveClinicalCase(
        slug="seizure-history-bupropion-reinterpretation",
        summary="Reinterpretar indicacion de bupropion al conocerse antecedente de convulsiones.",
        user_message=(
            "Psiquiatria documenta antecedente de crisis convulsiva en 2023. "
            "Actualiza antecedentes relevantes, enfermedad actual, analisis clinico y plan, "
            "y elimina cualquier instruccion de iniciar bupropion."
        ),
        target_document_id="99",
        target_document_title="Nota clinica salud mental",
        target_document_type="note",
        target_document_content=dedent(
            """
            ANTECEDENTES RELEVANTES:
            - Trastorno depresivo mayor.
            - Niega antecedente neurologico relevante.

            ENFERMEDAD ACTUAL:
            Anhedonia y fatiga persistentes. Se considera bupropion por baja energia y sintomas afectivos.

            ANALISIS CLINICO:
            Candidata para iniciar bupropion sin contraindicaciones documentadas al momento.

            PLAN:
            Iniciar bupropion XL 150 mg cada dia y control en 2 semanas.
            """
        ).strip(),
        supporting_context=(
            {
                "document_id": "ctx-seizure-1",
                "title": "Resumen neurologia",
                "type": "specialist_note",
                "read_mode": "supporting_context",
                "excerpt": "Antecedente de crisis tonico clonica generalizada en 2023, en seguimiento neurologico sin recurrencia reciente.",
            },
        ),
        affected_sections=(
            "antecedentes_relevantes",
            "enfermedad_actual",
            "analisis_clinico",
            "plan",
        ),
        edit_scope="reinterpretation",
        clinical_impact_level="clinical",
    ),
    LiveClinicalCase(
        slug="copd-home-oxygen-propagation",
        summary="Propagar dependencia de oxigeno domiciliario a la nota de EPOC.",
        user_message=(
            "Neumologia confirma uso basal de oxigeno domiciliario a 2 L/min. "
            "Actualiza antecedentes relevantes, enfermedad actual, analisis clinico y plan, y corrige cualquier texto que diga que no requiere oxigeno en casa."
        ),
        target_document_id="99",
        target_document_title="Nota clinica EPOC",
        target_document_type="note",
        target_document_content=dedent(
            """
            ANTECEDENTES RELEVANTES:
            - EPOC GOLD D.
            - Niega uso de oxigeno domiciliario.

            ENFERMEDAD ACTUAL:
            Disnea habitual al esfuerzo, sin incremento franco de secreciones. Sigue inhaladores de mantenimiento.

            ANALISIS CLINICO:
            EPOC severo en seguimiento, actualmente sin soporte cronico adicional documentado.

            PLAN:
            Continuar broncodilatadores inhalados y control por neumologia.
            """
        ).strip(),
        supporting_context=(
            {
                "document_id": "ctx-copd-1",
                "title": "Control neumologia",
                "type": "specialist_note",
                "read_mode": "supporting_context",
                "excerpt": "Paciente usa oxigeno domiciliario basal a 2 L/min por hipoxemia cronica. SatO2 habitual 90-91% con soporte.",
            },
        ),
        affected_sections=(
            "antecedentes_relevantes",
            "enfermedad_actual",
            "analisis_clinico",
            "plan",
        ),
        edit_scope="propagation",
        clinical_impact_level="factual",
    ),
    LiveClinicalCase(
        slug="neutropenic-fever-risk-reinterpretation",
        summary="Reinterpretar fiebre en paciente neutropenica como urgencia oncologica.",
        user_message=(
            "Hemograma reporta neutrofilos absolutos de 400 y fiebre de 38.6 C. "
            "Actualiza enfermedad actual, impresion diagnostica, analisis clinico y plan, y elimina cualquier descripcion de cuadro viral leve sin riesgo."
        ),
        target_document_id="99",
        target_document_title="Nota clinica oncologia",
        target_document_type="note",
        target_document_content=dedent(
            """
            ENFERMEDAD ACTUAL:
            Paciente en quimioterapia reciente por linfoma, con odinofagia y malestar general. Hasta ahora se interpreto como posible virosis autolimitada.

            IMPRESION DIAGNOSTICA:
            Infeccion respiratoria alta probablemente viral.

            ANALISIS CLINICO:
            Cuadro leve, sin datos de alto riesgo documentados en la ultima nota.

            PLAN:
            Manejo sintomatico, hidratacion y vigilancia ambulatoria.
            """
        ).strip(),
        supporting_context=(
            {
                "document_id": "ctx-neutro-1",
                "title": "Laboratorio hematologia",
                "type": "lab_result",
                "read_mode": "supporting_context",
                "excerpt": "Recuento absoluto de neutrofilos 400/uL. Temperatura documentada 38.6 C en admision.",
            },
        ),
        affected_sections=(
            "enfermedad_actual",
            "impresion_diagnostica",
            "analisis_clinico",
            "plan",
        ),
        edit_scope="reinterpretation",
        clinical_impact_level="clinical",
    ),
    LiveClinicalCase(
        slug="mrsa-history-antibiotic-change",
        summary="Reinterpretar antibiotico empirico por antecedente reciente de MRSA.",
        user_message=(
            "Hay antecedente de cultivo positivo para MRSA hace 2 meses. "
            "Actualiza antecedentes relevantes, impresion diagnostica, analisis clinico y plan, y corrige cualquier frase que descarte cobertura anti-MRSA."
        ),
        target_document_id="99",
        target_document_title="Nota clinica celulitis",
        target_document_type="note",
        target_document_content=dedent(
            """
            ANTECEDENTES RELEVANTES:
            - Diabetes mellitus tipo 2.
            - Sin germenes multirresistentes documentados.

            IMPRESION DIAGNOSTICA:
            Celulitis no purulenta de miembro inferior izquierdo.

            ANALISIS CLINICO:
            Riesgo bajo de patogenos resistentes con base en la informacion actual.

            PLAN:
            Iniciar cefalexina por via oral y seguimiento ambulatorio.
            """
        ).strip(),
        supporting_context=(
            {
                "document_id": "ctx-mrsa-1",
                "title": "Microbiologia previa",
                "type": "lab_result",
                "read_mode": "supporting_context",
                "excerpt": "Cultivo de absceso cutaneo positivo para MRSA hace 2 meses, sensible a clindamicina y trimetoprim-sulfametoxazol.",
            },
        ),
        affected_sections=(
            "antecedentes_relevantes",
            "impresion_diagnostica",
            "analisis_clinico",
            "plan",
        ),
        edit_scope="reinterpretation",
        clinical_impact_level="clinical",
    ),
    LiveClinicalCase(
        slug="insulin-start-hyperglycemia-propagation",
        summary="Propagar inicio de insulina basal por hiperglucemia sostenida.",
        user_message=(
            "Endocrinologia inicio insulina glargina 10 unidades nocturnas por glucosas persistentes mayores de 300. "
            "Actualiza antecedentes relevantes, enfermedad actual, analisis clinico y plan, y elimina cualquier texto que diga manejo solo con metformina."
        ),
        target_document_id="99",
        target_document_title="Nota clinica diabetes",
        target_document_type="note",
        target_document_content=dedent(
            """
            ANTECEDENTES RELEVANTES:
            - Diabetes mellitus tipo 2 tratada con metformina.

            ENFERMEDAD ACTUAL:
            Polidipsia y poliuria en las ultimas semanas. Mantiene tratamiento oral habitual.

            ANALISIS CLINICO:
            Descontrol glucemico pendiente de nueva valoracion, aun en manejo solo con antidiabeticos orales.

            PLAN:
            Continuar metformina, reforzar dieta y control en consulta externa.
            """
        ).strip(),
        supporting_context=(
            {
                "document_id": "ctx-insulin-1",
                "title": "Interconsulta endocrinologia",
                "type": "specialist_note",
                "read_mode": "supporting_context",
                "excerpt": "Glucemias capilares entre 310 y 360 mg/dL. Se inicia insulina glargina 10 U nocturnas desde hoy.",
            },
        ),
        affected_sections=(
            "antecedentes_relevantes",
            "enfermedad_actual",
            "analisis_clinico",
            "plan",
        ),
        edit_scope="propagation",
        clinical_impact_level="factual",
    ),
    LiveClinicalCase(
        slug="afib-anticoagulation-bleeding-reassessment",
        summary="Reinterpretar anticoagulacion en fibrilacion auricular por melena activa.",
        user_message=(
            "La paciente presento melena hoy y se sospecha sangrado digestivo alto. "
            "Actualiza enfermedad actual, impresion diagnostica, analisis clinico y plan, y quita cualquier orden de continuar anticoagulacion oral sin cambios."
        ),
        target_document_id="99",
        target_document_title="Nota clinica cardiologia",
        target_document_type="note",
        target_document_content=dedent(
            """
            ENFERMEDAD ACTUAL:
            Fibrilacion auricular en seguimiento, sin eventos recientes. Tolera anticoagulacion oral y permanece hemodinamicamente estable.

            IMPRESION DIAGNOSTICA:
            Fibrilacion auricular cronicamente anticoagulada, sin complicaciones actuales.

            ANALISIS CLINICO:
            Se prioriza prevencion tromboembolica; no hay datos nuevos que modifiquen la estrategia actual.

            PLAN:
            Continuar rivaroxaban 20 mg al dia y control por consulta externa.
            """
        ).strip(),
        supporting_context=(
            {
                "document_id": "ctx-bleed-1",
                "title": "Hoja urgencias",
                "type": "encounter_fact",
                "read_mode": "supporting_context",
                "excerpt": "Refiere dos evacuaciones melenaicas hoy. Se sospecha sangrado digestivo alto y se solicita valoracion por gastroenterologia.",
            },
        ),
        affected_sections=(
            "enfermedad_actual",
            "impresion_diagnostica",
            "analisis_clinico",
            "plan",
        ),
        edit_scope="reinterpretation",
        clinical_impact_level="clinical",
    ),
    LiveClinicalCase(
        slug="appendicitis-ct-confirmation-reinterpretation",
        summary="Reinterpretar dolor abdominal tras tomografia compatible con apendicitis.",
        user_message=(
            "La tomografia confirma apendicitis aguda no complicada. "
            "Actualiza enfermedad actual, impresion diagnostica, analisis clinico y plan, y elimina cualquier texto que la etiquete como gastroenteritis inespecifica."
        ),
        target_document_id="99",
        target_document_title="Nota clinica urgencias abdominal",
        target_document_type="note",
        target_document_content=dedent(
            """
            ENFERMEDAD ACTUAL:
            Dolor abdominal de 12 horas con nauseas. Al inicio se considero cuadro gastrointestinal inespecifico.

            IMPRESION DIAGNOSTICA:
            Gastroenteritis probable.

            ANALISIS CLINICO:
            Por ahora no hay evidencia documentada de patologia quirurgica abdominal.

            PLAN:
            Hidratacion, analgesia y observacion clinica.
            """
        ).strip(),
        supporting_context=(
            {
                "document_id": "ctx-appendix-1",
                "title": "Reporte tomografia",
                "type": "study_result",
                "read_mode": "supporting_context",
                "excerpt": "Tomografia abdominal: apendicitis aguda no complicada, apendice de 11 mm con cambios inflamatorios periappendiculares.",
            },
        ),
        affected_sections=(
            "enfermedad_actual",
            "impresion_diagnostica",
            "analisis_clinico",
            "plan",
        ),
        edit_scope="reinterpretation",
        clinical_impact_level="clinical",
    ),
    LiveClinicalCase(
        slug="pe-confirmed-anticoagulation-start",
        summary="Reinterpretar disnea tras confirmar tromboembolismo pulmonar.",
        user_message=(
            "La angiotomografia confirma embolia pulmonar segmentaria derecha. "
            "Actualiza enfermedad actual, impresion diagnostica, analisis clinico y plan, y elimina cualquier descripcion de ansiedad como unica causa."
        ),
        target_document_id="99",
        target_document_title="Nota clinica disnea aguda",
        target_document_type="note",
        target_document_content=dedent(
            """
            ENFERMEDAD ACTUAL:
            Disnea subita y opresion toracica. En la valoracion inicial se considero crisis de ansiedad.

            IMPRESION DIAGNOSTICA:
            Probable episodio ansioso.

            ANALISIS CLINICO:
            Sin datos concluyentes de patologia cardiopulmonar aguda con la informacion previa.

            PLAN:
            Observacion, ansiolisis si precisa y reevaluacion clinica.
            """
        ).strip(),
        supporting_context=(
            {
                "document_id": "ctx-pe-1",
                "title": "Angiotomografia pulmonar",
                "type": "study_result",
                "read_mode": "supporting_context",
                "excerpt": "Angiotomografia: defecto de llenado segmentario en arteria pulmonar derecha compatible con embolia pulmonar aguda.",
            },
        ),
        affected_sections=(
            "enfermedad_actual",
            "impresion_diagnostica",
            "analisis_clinico",
            "plan",
        ),
        edit_scope="reinterpretation",
        clinical_impact_level="clinical",
    ),
)


def all_live_clinical_cases() -> tuple[LiveClinicalCase, ...]:
    raw_exact = str(os.getenv("EVAL_CASE_EXACT") or "").strip()
    if raw_exact:
        try:
            exact_index = int(raw_exact)
        except ValueError:
            return _CASES
        if 1 <= exact_index <= len(_CASES):
            return (_CASES[exact_index - 1],)
        return _CASES

    raw_limit = str(os.getenv("EVAL_CASE_LIMIT") or "").strip()
    if not raw_limit:
        return _CASES
    try:
        limit = int(raw_limit)
    except ValueError:
        return _CASES
    if limit <= 0:
        return _CASES
    return _CASES[:limit]


def get_live_clinical_case(slug: str) -> LiveClinicalCase:
    for case in _CASES:
        if case.slug == slug:
            return case
    raise KeyError(f"Unknown live clinical case: {slug}")


def build_target_document(case: LiveClinicalCase) -> dict[str, Any]:
    return {
        "document_id": case.target_document_id,
        "title": case.target_document_title,
        "type": case.target_document_type,
        "version": 9,
        "status": "active",
        "is_active": True,
        "is_open": True,
        "ai_writable": True,
    }


def build_document_read(case: LiveClinicalCase) -> dict[str, Any]:
    return {
        "document_id": case.target_document_id,
        "encounter_id": "eval-encounter",
        "title": case.target_document_title,
        "type": case.target_document_type,
        "version": 9,
        "content_hash": f"hash-{case.slug}",
        "updated_at": "2026-04-03T10:00:00Z",
        "mode": "full",
        "content": case.target_document_content,
        "excerpt": case.target_document_content,
        "short_summary": case.summary,
    }


def build_clinical_plan(case: LiveClinicalCase) -> dict[str, Any]:
    return {
        "edit_scope": case.edit_scope,
        "clinical_impact_level": case.clinical_impact_level,
        "affected_sections": list(case.affected_sections),
        "needs_full_note": True,
        "needs_external_knowledge": False,
    }


def build_eval_state(case: LiveClinicalCase) -> dict[str, Any]:
    target_document = build_target_document(case)
    read_document = build_document_read(case)
    selected_document_ids = list(case.selected_document_ids) or [case.target_document_id]
    workspace_documents = [dict(document) for document in case.workspace_documents] or [
        {
            **target_document,
            "short_summary": case.summary,
        }
    ]
    document_summaries = {
        str(document["document_id"]): {
            "title": document["title"],
            "type": document["type"],
            "version": document.get("version", 1),
            "short_summary": str(document.get("short_summary") or case.summary),
        }
        for document in workspace_documents
    }

    return {
        "tenant_id": "doctor:eval",
        "user_id": "doctor:eval",
        "encounter_id": "eval-encounter",
        "active_document_id": case.target_document_id,
        "thread_id": f"copilot:evaluations:{case.slug}",
        "user_message": case.user_message,
        "workspace_index": {
            "encounter_id": "eval-encounter",
            "workspace_version": "eval-v1",
            "active_document_id": case.target_document_id,
            "open_document_ids": selected_document_ids,
            "documents": workspace_documents,
        },
        "messages": [HumanMessage(content=case.user_message)],
        "selected_document_ids": selected_document_ids,
        "available_documents": workspace_documents,
        "context_view": None,
        "document_summaries": document_summaries,
        "document_reads": [read_document],
        "read_spans": [],
        "retrieved_context": list(case.supporting_context),
        "read_documents": [read_document],
        "encounter_context": None,
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
        "max_patch_operations": max(len(case.affected_sections), 1),
        "planner_retry_count": 0,
        "last_planner_error": None,
        "last_tool_error": None,
        "target_document_id": None,
        "target_document_title": None,
        "target_selection_reason": None,
        "base_version": None,
        "patch_set_preview": None,
        "patch_preview": None,
        "patch_id": None,
        "final_response": None,
        "requires_human_review": False,
        "review_result": None,
        "review_comment": None,
        "run_error": None,
        "trace_metadata": {"eval_case": case.slug},
        "clinical_plan": build_clinical_plan(case),
    }