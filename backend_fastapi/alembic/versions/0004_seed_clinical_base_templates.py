"""Seed clinical base templates for new doctors."""

from __future__ import annotations

from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


OMIT_IF_MISSING = (
    "Solo incluir si fue mencionado explicitamente en la transcripcion, "
    "el contexto clinico o los datos del paciente; si no, omitir."
)

GENERAL_RULES = (
    "Reglas generales: usa Markdown clinico con encabezados ## y ###; "
    "no uses listas con vinetas (-) para subtitulos ni subsecciones; "
    "redacta cada seccion en prosa clinica bajo su encabezado; "
    "no inventes signos vitales, diagnosticos, antecedentes, medicamentos, "
    "resultados, ordenes ni incapacidades; diferencia informacion referida "
    "por paciente o acompanante de hallazgos del profesional."
)

ADMIN_HEADER = f"""
({GENERAL_RULES})

## Identificacion del documento
[Tipo de documento clinico, fecha y hora de atencion, modalidad, sede o IPS, servicio o especialidad] ({OMIT_IF_MISSING})

## Identificacion del paciente
[Nombre completo, tipo y numero de documento, fecha de nacimiento o edad, sexo registrado, telefono o contacto, asegurador o EAPB, acompanante si aplica] ({OMIT_IF_MISSING})

## Identificacion del profesional
[Nombre del profesional tratante, profesion o especialidad, registro profesional] ({OMIT_IF_MISSING})
""".strip()


BASE_TEMPLATES = [
    {
        "name": "Historia clinica de consulta externa - primera vez",
        "document_kind": "document",
        "content": f"""
{ADMIN_HEADER}

## Datos del encuentro
[Datos administrativos del encuentro: tipo de atencion consulta externa primera vez, fecha, hora, sede, servicio] ({OMIT_IF_MISSING})

## Motivo de consulta
[Motivo de consulta] ({OMIT_IF_MISSING})

## Fuente y confiabilidad de la informacion
[Fuente de la informacion y confiabilidad: paciente, acompanante, remision, historia previa u otra] ({OMIT_IF_MISSING})

## Enfermedad actual
[Enfermedad actual descrita de forma cronologica, clara y clinica] ({OMIT_IF_MISSING} Incluir inicio, duracion, localizacion, caracteristicas, intensidad, factores desencadenantes, factores de alivio o empeoramiento, sintomas asociados, tratamientos previos y respuesta cuando esten mencionados.)

## Antecedentes
[Antecedentes patologicos, quirurgicos, traumaticos, alergicos, farmacologicos o medicamentos actuales, familiares, gineco-obstetricos si aplica, habitos toxicos, exposiciones, sociales y otros relevantes] ({OMIT_IF_MISSING})

## Revision por sistemas
[Revision por sistemas con sintomas referidos o negados relevantes al motivo de consulta; no extender a todos los sistemas si no hay informacion] ({OMIT_IF_MISSING})

## Signos vitales y medidas antropometricas
[Presion arterial, frecuencia cardiaca, frecuencia respiratoria, temperatura, saturacion de oxigeno, peso, talla, IMC, escala de dolor u otras medidas mencionadas] ({OMIT_IF_MISSING})

## Examen fisico
[Examen fisico general y dirigido al motivo de consulta] ({OMIT_IF_MISSING} No crear hallazgos negativos no mencionados.)

## Resultados disponibles
[Resultados de laboratorios, imagenes, procedimientos previos u otros estudios disponibles al momento de la consulta] ({OMIT_IF_MISSING})

## Analisis clinico
[Analisis e interpretacion del caso] ({OMIT_IF_MISSING} No agregar diagnosticos no sustentados por la fuente.)

## Diagnosticos
[Diagnostico principal, diagnosticos relacionados y diagnosticos diferenciales con codigo si fue mencionado] ({OMIT_IF_MISSING})

## Medicamentos formulados
[Medicamentos formulados con dosis, via, frecuencia y duracion] ({OMIT_IF_MISSING})

## Examenes, procedimientos e interconsultas
[Examenes solicitados, procedimientos solicitados o realizados, interconsultas o remisiones] ({OMIT_IF_MISSING})

## Recomendaciones, educacion y signos de alarma
[Recomendaciones no farmacologicas, educacion al paciente y signos de alarma explicados] ({OMIT_IF_MISSING})

## Incapacidad
[Incapacidad medica si aplica] ({OMIT_IF_MISSING})

## Control y seguimiento
[Control o seguimiento programado] ({OMIT_IF_MISSING})

## Comprension del plan
[Comprension y aceptacion del plan por el paciente o acompanante] ({OMIT_IF_MISSING})

## Profesional responsable
[Profesional responsable de la atencion] ({OMIT_IF_MISSING})
""".strip(),
    },
    {
        "name": "Historia clinica de consulta externa - control",
        "document_kind": "document",
        "content": f"""
{ADMIN_HEADER}

## Datos del encuentro
[Datos administrativos del encuentro: tipo de atencion consulta externa de control, fecha, hora, sede, servicio] ({OMIT_IF_MISSING})

## Motivo y objetivo del control
[Motivo y objetivo del control; no repetir la historia inicial completa] ({OMIT_IF_MISSING})

## Problemas o diagnosticos activos
[Problemas o diagnosticos activos en seguimiento] ({OMIT_IF_MISSING})

## Evolucion desde la ultima consulta
[Evolucion clinica desde la ultima consulta] ({OMIT_IF_MISSING})

## Sintomas nuevos o persistentes
[Sintomas nuevos o persistentes] ({OMIT_IF_MISSING})

## Atenciones recientes
[Consultas, urgencias u hospitalizaciones recientes] ({OMIT_IF_MISSING})

## Adherencia al tratamiento
[Adherencia al tratamiento, barreras y dificultades reportadas] ({OMIT_IF_MISSING})

## Respuesta terapeutica
[Respuesta terapeutica al manejo actual] ({OMIT_IF_MISSING})

## Efectos adversos
[Efectos adversos y barreras al tratamiento] ({OMIT_IF_MISSING})

## Medicamentos actuales y cambios
[Medicamentos actuales y cambios realizados o planeados] ({OMIT_IF_MISSING})

## Resultados de estudios
[Resultados de laboratorios, imagenes o procedimientos revisados en el control] ({OMIT_IF_MISSING})

## Antecedentes o alergias nuevas
[Antecedentes o alergias nuevas desde la ultima atencion] ({OMIT_IF_MISSING})

## Signos vitales
[Signos vitales y medidas del control] ({OMIT_IF_MISSING})

## Examen fisico dirigido
[Examen fisico dirigido a los problemas activos] ({OMIT_IF_MISSING})

## Analisis por problema activo
Redactar un bloque separado por cada problema o diagnostico activo, no un solo parrafo mezclando todos los problemas.

### [Problema o diagnostico activo 1]
[Evolucion, interpretacion y conducta para este problema] ({OMIT_IF_MISSING})

### [Problema o diagnostico activo 2]
[Evolucion, interpretacion y conducta para este problema] ({OMIT_IF_MISSING})

## Estado de las metas clinicas
[Estado de las metas clinicas acordadas] ({OMIT_IF_MISSING})

## Ajustes del manejo
[Ajustes del manejo por problema activo] ({OMIT_IF_MISSING})

## Nuevas ordenes
[Nuevas ordenes de examenes, procedimientos, interconsultas o remisiones] ({OMIT_IF_MISSING})

## Recomendaciones y signos de alarma
[Recomendaciones, educacion y signos de alarma] ({OMIT_IF_MISSING})

## Proximo control
[Fecha o criterio del proximo control] ({OMIT_IF_MISSING})

## Profesional responsable
[Profesional responsable de la atencion] ({OMIT_IF_MISSING})
""".strip(),
    },
    {
        "name": "Historia clinica de teleconsulta",
        "document_kind": "document",
        "content": f"""
{ADMIN_HEADER}

## Datos del encuentro
[Datos administrativos del encuentro: tipo de atencion teleconsulta, fecha, hora, sede o IPS, servicio] ({OMIT_IF_MISSING})

## Tipo de teleatencion
[Tipo de teleatencion: sincrona, asincrona u otra modalidad mencionada] ({OMIT_IF_MISSING})

## Verificacion de identidad
[Verificacion de identidad del paciente] ({OMIT_IF_MISSING})

## Ubicacion actual del paciente
[Ubicacion actual del paciente durante la consulta] ({OMIT_IF_MISSING})

## Personas presentes
[Personas presentes durante la consulta] ({OMIT_IF_MISSING})

## Motivo de consulta
[Motivo de consulta] ({OMIT_IF_MISSING})

## Fuente de la informacion
[Fuente de la informacion y confiabilidad] ({OMIT_IF_MISSING})

## Consentimiento para la modalidad
[Consentimiento informado para la modalidad de teleatencion] ({OMIT_IF_MISSING})

## Enfermedad actual
[Enfermedad actual descrita de forma cronologica y clinica] ({OMIT_IF_MISSING})

## Antecedentes relevantes
[Antecedentes patologicos, quirurgicos, alergicos, farmacologicos, familiares, sociales, toxicos y otros relevantes] ({OMIT_IF_MISSING})

## Revision por sistemas
[Revision por sistemas con sintomas referidos o negados relevantes al motivo de consulta] ({OMIT_IF_MISSING})

## Signos vitales informados por el paciente
[Signos vitales y medidas antropometricas informados por el paciente o medidos con dispositivos remotos; indicar dispositivos utilizados si fueron mencionados] ({OMIT_IF_MISSING})

## Hallazgos observados por video
[Hallazgos observados por video durante la teleconsulta] ({OMIT_IF_MISSING} No escribir "examen fisico normal" si no hubo evaluacion presencial completa.)

## Maniobras guiadas
[Maniobras guiadas realizadas durante la teleconsulta] ({OMIT_IF_MISSING})

## Documentos o imagenes aportados
[Documentos, imagenes u otros aportes del paciente revisados durante la consulta] ({OMIT_IF_MISSING})

## Limitaciones del examen remoto
[Limitaciones del examen remoto y elementos no evaluados] ({OMIT_IF_MISSING})

## Resultados disponibles
[Resultados de laboratorios, imagenes u otros estudios disponibles] ({OMIT_IF_MISSING})

## Analisis clinico
[Analisis e interpretacion del caso con nivel de certeza de la valoracion remota] ({OMIT_IF_MISSING})

## Diagnosticos
[Diagnostico principal, diagnosticos relacionados y diagnosticos diferenciales] ({OMIT_IF_MISSING})

## Necesidad de atencion presencial
[Necesidad de atencion presencial o estudios complementarios] ({OMIT_IF_MISSING})

## Criterios para acudir a urgencias
[Criterios para acudir a urgencias explicados al paciente] ({OMIT_IF_MISSING})

## Plan de manejo
[Medicamentos formulados, examenes, procedimientos, interconsultas, recomendaciones y signos de alarma] ({OMIT_IF_MISSING})

## Control y seguimiento
[Control o seguimiento programado] ({OMIT_IF_MISSING})

## Comprension del plan
[Comprension y aceptacion del plan] ({OMIT_IF_MISSING})

## Profesional responsable
[Profesional responsable de la atencion] ({OMIT_IF_MISSING})
""".strip(),
    },
    {
        "name": "Historia clinica de urgencias - valoracion inicial",
        "document_kind": "document",
        "content": f"""
{ADMIN_HEADER}

## Datos del ingreso
[Fecha y hora de ingreso y de valoracion inicial, forma de llegada, acompanante o responsable, fuente de informacion] ({OMIT_IF_MISSING})

## Clasificacion de triage
[Clasificacion de triage] ({OMIT_IF_MISSING})

## Motivo de consulta
[Motivo de consulta] ({OMIT_IF_MISSING})

## Inicio del evento
[Hora o fecha de inicio del evento actual] ({OMIT_IF_MISSING})

## Enfermedad actual
[Enfermedad actual con cronologia precisa] ({OMIT_IF_MISSING} Priorizar tiempo de evolucion, sintoma principal, severidad, sintomas de alarma y manejo previo al ingreso.)

## Atencion previa al ingreso
[Atencion, medicamentos o medidas recibidas antes del ingreso a urgencias] ({OMIT_IF_MISSING})

## Antecedentes inmediatamente relevantes
[Antecedentes patologicos, quirurgicos y otros inmediatamente relevantes para el evento actual] ({OMIT_IF_MISSING})

## Alergias y medicamentos actuales
[Alergias y medicamentos que usa el paciente al ingreso] ({OMIT_IF_MISSING})

## Signos vitales iniciales
[Signos vitales iniciales y escala de dolor] ({OMIT_IF_MISSING})

## Estado neurologico
[Estado neurologico cuando aplique] ({OMIT_IF_MISSING})

## Examen fisico dirigido
[Examen fisico dirigido al motivo de consulta] ({OMIT_IF_MISSING})

## Resultados disponibles
[Resultados de laboratorios, imagenes u otros estudios disponibles al momento de la valoracion inicial] ({OMIT_IF_MISSING})

## Analisis inicial
[Analisis inicial del caso] ({OMIT_IF_MISSING})

## Diagnosticos o posibilidades diagnosticas
[Diagnostico principal, diagnosticos relacionados y posibilidades diagnosticas] ({OMIT_IF_MISSING})

## Medicamentos indicados
[Medicamentos indicados u ordenados durante la valoracion inicial, sin confundir con administrados ni formulados al egreso] ({OMIT_IF_MISSING})

## Medicamentos administrados
[Medicamentos administrados en urgencias durante la valoracion inicial] ({OMIT_IF_MISSING})

## Procedimientos realizados
[Procedimientos realizados durante la valoracion inicial] ({OMIT_IF_MISSING})

## Examenes y ordenes
[Examenes, imagenes u otras ordenes solicitadas] ({OMIT_IF_MISSING})

## Conducta inicial
[Conducta inicial: observacion, alta, remision u hospitalizacion segun lo definido en esta valoracion] ({OMIT_IF_MISSING})

## Profesional responsable
[Profesional responsable de la valoracion inicial] ({OMIT_IF_MISSING})
""".strip(),
    },
    {
        "name": "Nota de evolucion y egreso de urgencias",
        "document_kind": "document",
        "content": f"""
{ADMIN_HEADER}

## Tipo de nota
[Tipo de nota: revaloracion intermedia, evolucion en observacion o nota de egreso final] ({OMIT_IF_MISSING})

## Datos de la revaloracion
[Fecha y hora de la revaloracion y tiempo transcurrido desde la valoracion inicial o ultima nota] ({OMIT_IF_MISSING})

## Evolucion clinica
[Evolucion clinica desde la valoracion inicial o ultima revaloracion] ({OMIT_IF_MISSING})

## Nuevos sintomas o eventos
[Nuevos sintomas o eventos ocurridos durante la estancia en urgencias] ({OMIT_IF_MISSING})

## Signos vitales de control
[Signos vitales de control] ({OMIT_IF_MISSING})

## Examen fisico de seguimiento
[Examen fisico de seguimiento] ({OMIT_IF_MISSING})

## Resultados de estudios
[Resultados de laboratorios, imagenes u otros estudios obtenidos durante la estancia] ({OMIT_IF_MISSING})

## Tratamientos administrados
[Tratamientos y medicamentos administrados durante la estancia en urgencias] ({OMIT_IF_MISSING})

## Respuesta al tratamiento
[Respuesta al tratamiento instaurado] ({OMIT_IF_MISSING})

## Diagnosticos actualizados
[Diagnosticos actualizados con base en la evolucion y resultados] ({OMIT_IF_MISSING})

## Analisis y justificacion de la conducta
[Analisis e interpretacion que justifica la conducta adoptada] ({OMIT_IF_MISSING})

## Condicion al egreso
[Condicion clinica del paciente al momento del egreso o traslado] ({OMIT_IF_MISSING})

## Conducta final
[Alta, hospitalizacion, remision o traslado segun corresponda] ({OMIT_IF_MISSING})

## Formula de egreso
[Medicamentos formulados al egreso, distinguiendolos de los administrados durante la estancia] ({OMIT_IF_MISSING})

## Recomendaciones
[Recomendaciones al egreso] ({OMIT_IF_MISSING})

## Signos de alarma
[Signos de alarma explicados al paciente o acompanante] ({OMIT_IF_MISSING})

## Seguimiento
[Seguimiento ambulatorio, control o interconsulta programada] ({OMIT_IF_MISSING})

## Incapacidad
[Incapacidad medica si aplica] ({OMIT_IF_MISSING})

## Profesional responsable
[Profesional responsable de la nota] ({OMIT_IF_MISSING})
""".strip(),
    },
    {
        "name": "Nota de procedimiento",
        "document_kind": "document",
        "content": f"""
{ADMIN_HEADER}

## Datos del procedimiento
[Procedimiento realizado, fecha, hora, sitio anatomico, lateralidad y profesional que realiza] ({OMIT_IF_MISSING})

## Indicacion
[Indicacion del procedimiento] ({OMIT_IF_MISSING})

## Diagnostico relacionado
[Diagnostico relacionado] ({OMIT_IF_MISSING})

## Procedimiento planeado
[Procedimiento planeado y comparacion con el realizado si hubo cambio] ({OMIT_IF_MISSING})

## Verificacion de identidad
[Verificacion de identidad del paciente] ({OMIT_IF_MISSING})

## Consentimiento informado
[Consentimiento informado cuando aplique] ({OMIT_IF_MISSING})

## Riesgos o precauciones relevantes
[Riesgos o precauciones relevantes explicados o considerados] ({OMIT_IF_MISSING})

## Alergias
[Alergias relevantes verificadas] ({OMIT_IF_MISSING})

## Lista de verificacion o pausa de seguridad
[Lista de verificacion o pausa de seguridad aplicada] ({OMIT_IF_MISSING})

## Preparacion, asepsia y antisepsia
[Preparacion del sitio, asepsia y antisepsia] ({OMIT_IF_MISSING})

## Anestesia o analgesia
[Anestesia o analgesia utilizada] ({OMIT_IF_MISSING})

## Tecnica realizada
[Descripcion de la tecnica realizada] ({OMIT_IF_MISSING})

## Materiales y dispositivos
[Materiales y dispositivos utilizados] ({OMIT_IF_MISSING})

## Hallazgos
[Hallazgos durante el procedimiento] ({OMIT_IF_MISSING})

## Muestras obtenidas
[Muestras obtenidas y destino si aplica] ({OMIT_IF_MISSING})

## Resultado del procedimiento
[Resultado del procedimiento] ({OMIT_IF_MISSING})

## Eventos o complicaciones
[Eventos adversos o complicaciones ocurridas] ({OMIT_IF_MISSING} No prellenar "sin complicaciones" ni "toleró adecuadamente" si no fueron mencionados.)

## Condicion del paciente al finalizar
[Condicion del paciente al finalizar el procedimiento] ({OMIT_IF_MISSING})

## Cuidados posteriores
[Cuidados posteriores indicados] ({OMIT_IF_MISSING})

## Medicamentos
[Medicamentos indicados posterior al procedimiento] ({OMIT_IF_MISSING})

## Recomendaciones y signos de alarma
[Recomendaciones y signos de alarma] ({OMIT_IF_MISSING})

## Control
[Control o seguimiento programado] ({OMIT_IF_MISSING})

## Profesional responsable
[Profesional responsable del procedimiento] ({OMIT_IF_MISSING})
""".strip(),
    },
    {
        "name": "Nota de interconsulta o concepto especializado",
        "document_kind": "document",
        "content": f"""
{ADMIN_HEADER}

## Servicio o profesional solicitante
[Servicio o profesional que solicita la interconsulta] ({OMIT_IF_MISSING})

## Motivo de la interconsulta
[Motivo concreto de la interconsulta] ({OMIT_IF_MISSING})

## Pregunta clinica
[Pregunta clinica especifica que debe resolver el especialista] ({OMIT_IF_MISSING})

## Resumen del caso
[Resumen del caso] ({OMIT_IF_MISSING})

## Antecedentes relevantes
[Antecedentes patologicos, quirurgicos y otros relevantes para la consulta especializada] ({OMIT_IF_MISSING})

## Medicamentos y alergias
[Medicamentos actuales y alergias] ({OMIT_IF_MISSING})

## Resultados relevantes
[Resultados de laboratorios, imagenes u otros estudios relevantes] ({OMIT_IF_MISSING})

## Evaluacion del especialista
[Evaluacion realizada por el especialista] ({OMIT_IF_MISSING})

## Examen dirigido
[Examen fisico o evaluacion dirigida realizada por el especialista] ({OMIT_IF_MISSING})

## Analisis
[Analisis e interpretacion del caso desde la perspectiva especializada] ({OMIT_IF_MISSING})

## Impresion diagnostica
[Impresion diagnostica del especialista] ({OMIT_IF_MISSING})

## Recomendaciones
[Recomendaciones del especialista] ({OMIT_IF_MISSING})

## Medicamentos u ordenes sugeridas
[Medicamentos, examenes, procedimientos u ordenes sugeridas por el especialista] ({OMIT_IF_MISSING})

## Necesidad de seguimiento
[Necesidad de seguimiento por especialidad] ({OMIT_IF_MISSING})

## Criterios para nueva valoracion
[Criterios para nueva valoracion o reinterconsulta] ({OMIT_IF_MISSING})

## Comunicacion al equipo tratante
[Comunicacion del concepto al equipo tratante] ({OMIT_IF_MISSING})

## Profesional responsable
[Profesional especialista responsable del concepto] ({OMIT_IF_MISSING})""".strip(),
    },
]


def upgrade() -> None:
    templates_table = sa.table(
        "templates_basetemplate",
        sa.column("name", sa.String),
        sa.column("document_kind", sa.String),
        sa.column("content", sa.Text),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )

    connection = op.get_bind()
    created_at = datetime.now(UTC)
    for template in BASE_TEMPLATES:
        exists = connection.execute(
            sa.select(sa.literal(1)).where(
                sa.exists().where(
                    sa.and_(
                        templates_table.c.name == template["name"],
                        templates_table.c.document_kind == template["document_kind"],
                    )
                )
            )
        ).scalar_one_or_none()
        if exists:
            continue

        connection.execute(
            templates_table.insert().values(
                name=template["name"],
                document_kind=template["document_kind"],
                content=template["content"],
                created_at=created_at,
            )
        )


def downgrade() -> None:
    templates_table = sa.table(
        "templates_basetemplate",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("document_kind", sa.String),
    )
    doctor_templates_table = sa.table(
        "templates_doctortemplate",
        sa.column("base_template_id", sa.Integer),
    )
    op.get_bind().execute(
        templates_table.delete().where(
            sa.and_(
                templates_table.c.name.in_(
                    [template["name"] for template in BASE_TEMPLATES]
                ),
                ~sa.exists().where(
                    doctor_templates_table.c.base_template_id == templates_table.c.id
                ),
            )
        )
    )
