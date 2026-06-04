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

COMMON_HEADER = f"""
(Reglas generales: usa Markdown clinico; conserva encabezados y vinetas; no inventes signos vitales, diagnosticos, antecedentes, medicamentos, resultados, ordenes ni incapacidades; diferencia informacion referida por paciente o acompanante de hallazgos del profesional.)

## Identificacion del documento
- Tipo de documento clinico: [Tipo de documento clinico] ({OMIT_IF_MISSING})
- Fecha y hora de atencion: [Fecha y hora de atencion] ({OMIT_IF_MISSING})
- Modalidad: [Modalidad de atencion] ({OMIT_IF_MISSING})
- Sede / IPS / consultorio: [Sede, IPS o consultorio] ({OMIT_IF_MISSING})
- Servicio / especialidad: [Servicio o especialidad] ({OMIT_IF_MISSING})

## Identificacion del paciente
- Nombre completo: [Nombre completo del paciente] ({OMIT_IF_MISSING})
- Tipo y numero de documento: [Tipo y numero de documento del paciente] ({OMIT_IF_MISSING})
- Fecha de nacimiento / edad: [Fecha de nacimiento y edad] ({OMIT_IF_MISSING})
- Sexo registrado: [Sexo registrado] ({OMIT_IF_MISSING})
- Telefono / contacto: [Telefono o contacto] ({OMIT_IF_MISSING})
- Asegurador / EAPB / regimen: [Asegurador, EAPB o regimen] ({OMIT_IF_MISSING})
- Acompanante: [Nombre del acompanante y relacion] ({OMIT_IF_MISSING})

## Identificacion del profesional
- Profesional tratante: [Nombre del profesional tratante] ({OMIT_IF_MISSING})
- Profesion / especialidad: [Profesion o especialidad del profesional] ({OMIT_IF_MISSING})
- Registro profesional: [Registro profesional] ({OMIT_IF_MISSING})
""".strip()


BASE_TEMPLATES = [
    {
        "name": "Historia clinica de consulta externa",
        "document_kind": "document",
        "content": f"""
{COMMON_HEADER}

## Encabezado
- Tipo de atencion: Consulta externa
- Motivo de consulta: [Motivo de consulta] ({OMIT_IF_MISSING})
- Fuente de informacion: [Fuente de informacion: paciente, acompanante, remision, historia previa u otra] ({OMIT_IF_MISSING})
- Confiabilidad de la informacion: [Confiabilidad de la informacion] ({OMIT_IF_MISSING})

## Enfermedad actual
[Enfermedad actual descrita de forma cronologica, clara y clinica] ({OMIT_IF_MISSING} Incluir inicio, duracion, localizacion, caracteristicas, intensidad, factores desencadenantes, factores de alivio o empeoramiento, sintomas asociados, tratamientos previos y respuesta cuando esten mencionados. Escribir como parrafo clinico.)

## Antecedentes
- Patologicos: [Antecedentes patologicos] ({OMIT_IF_MISSING})
- Quirurgicos: [Antecedentes quirurgicos] ({OMIT_IF_MISSING})
- Traumaticos: [Antecedentes traumaticos] ({OMIT_IF_MISSING})
- Alergicos: [Alergias, severidad y reaccion] ({OMIT_IF_MISSING})
- Farmacologicos / medicamentos actuales: [Medicamentos actuales con dosis y frecuencia] ({OMIT_IF_MISSING})
- Familiares: [Antecedentes familiares] ({OMIT_IF_MISSING})
- Gineco-obstetricos: [Antecedentes gineco-obstetricos] ({OMIT_IF_MISSING})
- Toxicos / exposiciones: [Habitos toxicos y exposiciones relevantes] ({OMIT_IF_MISSING})
- Vacunacion: [Vacunacion relevante] ({OMIT_IF_MISSING})
- Otros relevantes: [Otros antecedentes relevantes] ({OMIT_IF_MISSING})

## Revision por sistemas
- General: [Revision general] ({OMIT_IF_MISSING})
- Cardiovascular: [Revision cardiovascular] ({OMIT_IF_MISSING})
- Respiratorio: [Revision respiratoria] ({OMIT_IF_MISSING})
- Gastrointestinal: [Revision gastrointestinal] ({OMIT_IF_MISSING})
- Genitourinario: [Revision genitourinaria] ({OMIT_IF_MISSING})
- Neurologico: [Revision neurologica] ({OMIT_IF_MISSING})
- Osteomuscular: [Revision osteomuscular] ({OMIT_IF_MISSING})
- Piel y anexos: [Revision de piel y anexos] ({OMIT_IF_MISSING})
- Salud mental / sueno / animo: [Revision de salud mental, sueno o animo] ({OMIT_IF_MISSING})
- Otros: [Otra revision por sistemas relevante] ({OMIT_IF_MISSING})

## Signos vitales
- Presion arterial: [Presion arterial] ({OMIT_IF_MISSING})
- Frecuencia cardiaca: [Frecuencia cardiaca] ({OMIT_IF_MISSING})
- Frecuencia respiratoria: [Frecuencia respiratoria] ({OMIT_IF_MISSING})
- Temperatura: [Temperatura] ({OMIT_IF_MISSING})
- Saturacion de oxigeno: [Saturacion de oxigeno] ({OMIT_IF_MISSING})
- Peso: [Peso] ({OMIT_IF_MISSING})
- Talla: [Talla] ({OMIT_IF_MISSING})
- IMC: [IMC] ({OMIT_IF_MISSING})
- Dolor: [Escala de dolor] ({OMIT_IF_MISSING})

## Examen fisico
- Estado general: [Estado general] ({OMIT_IF_MISSING})
- Cabeza y cuello: [Cabeza y cuello] ({OMIT_IF_MISSING})
- Cardiopulmonar: [Cardiopulmonar] ({OMIT_IF_MISSING})
- Abdomen: [Abdomen] ({OMIT_IF_MISSING})
- Extremidades: [Extremidades] ({OMIT_IF_MISSING})
- Neurologico: [Neurologico] ({OMIT_IF_MISSING})
- Piel: [Piel] ({OMIT_IF_MISSING})
- Examen especifico por especialidad: [Examen especifico por especialidad] ({OMIT_IF_MISSING})
- Hallazgos negativos relevantes: [Hallazgos negativos relevantes] ({OMIT_IF_MISSING} No crear negativos no mencionados.)

## Analisis clinico
[Resumen interpretativo del caso] ({OMIT_IF_MISSING} No agregar diagnosticos no sustentados por la fuente.)

## Diagnosticos
- Diagnostico principal: [Diagnostico principal y codigo si fue mencionado] ({OMIT_IF_MISSING})
- Diagnosticos relacionados: [Diagnosticos relacionados] ({OMIT_IF_MISSING})
- Diagnosticos diferenciales: [Diagnosticos diferenciales] ({OMIT_IF_MISSING})

## Plan de manejo
- Conducta general: [Conducta general] ({OMIT_IF_MISSING})
- Medicamentos formulados: [Medicamentos formulados con dosis, via, frecuencia y duracion] ({OMIT_IF_MISSING})
- Examenes solicitados: [Examenes solicitados] ({OMIT_IF_MISSING})
- Procedimientos solicitados o realizados: [Procedimientos solicitados o realizados] ({OMIT_IF_MISSING})
- Interconsultas / remisiones: [Interconsultas o remisiones] ({OMIT_IF_MISSING})
- Recomendaciones no farmacologicas: [Recomendaciones no farmacologicas] ({OMIT_IF_MISSING})
- Educacion al paciente: [Educacion brindada al paciente] ({OMIT_IF_MISSING})
- Signos de alarma: [Signos de alarma explicados] ({OMIT_IF_MISSING})
- Incapacidad medica: [Incapacidad medica] ({OMIT_IF_MISSING})
- Control / seguimiento: [Control o seguimiento] ({OMIT_IF_MISSING})

## Cierre
- Paciente entiende y acepta el plan: [Comprension y aceptacion del plan] ({OMIT_IF_MISSING})
- Observaciones: [Observaciones finales] ({OMIT_IF_MISSING})
- Profesional responsable: [Profesional responsable] ({OMIT_IF_MISSING})
""".strip(),
    },
    {
        "name": "Nota de evolucion o control",
        "document_kind": "document",
        "content": f"""
{COMMON_HEADER}

## Encabezado
- Tipo de atencion: Evolucion / control
- Motivo del control: [Motivo del control] ({OMIT_IF_MISSING})
- Diagnostico previo relevante: [Diagnostico previo relevante] ({OMIT_IF_MISSING})
- Tratamiento actual: [Tratamiento actual] ({OMIT_IF_MISSING})

## Subjetivo
[Informacion referida por el paciente o acompanante] ({OMIT_IF_MISSING} Incluir evolucion desde la ultima atencion, adherencia, efectos adversos, nuevos sintomas y dudas del paciente cuando esten mencionados.)

## Objetivo
- Signos vitales: [Signos vitales] ({OMIT_IF_MISSING})
- Hallazgos al examen fisico: [Hallazgos al examen fisico de control] ({OMIT_IF_MISSING})
- Resultados revisados: [Resultados revisados] ({OMIT_IF_MISSING})
- Cambios relevantes: [Cambios relevantes] ({OMIT_IF_MISSING})

## Analisis
[Analisis de evolucion] ({OMIT_IF_MISSING} Relacionar respuesta al tratamiento, estabilidad, deterioro o necesidad de ajuste solo si esta sustentado.)

## Plan
- Continuar: [Tratamientos o medidas a continuar] ({OMIT_IF_MISSING})
- Modificar: [Tratamientos o medidas a modificar] ({OMIT_IF_MISSING})
- Suspender: [Tratamientos o medidas a suspender] ({OMIT_IF_MISSING})
- Nuevas ordenes: [Nuevas ordenes] ({OMIT_IF_MISSING})
- Educacion y recomendaciones: [Educacion y recomendaciones] ({OMIT_IF_MISSING})
- Signos de alarma: [Signos de alarma] ({OMIT_IF_MISSING})
- Proximo control: [Proximo control] ({OMIT_IF_MISSING})

## Cierre
- Estado al finalizar la atencion: [Estado final] ({OMIT_IF_MISSING})
- Profesional responsable: [Profesional responsable] ({OMIT_IF_MISSING})
""".strip(),
    },
    {
        "name": "Historia clinica de urgencias",
        "document_kind": "document",
        "content": f"""
{COMMON_HEADER}

## Encabezado
- Tipo de atencion: Urgencias / atencion inmediata
- Fecha y hora de ingreso: [Fecha y hora de ingreso] ({OMIT_IF_MISSING})
- Medio de ingreso: [Medio de ingreso] ({OMIT_IF_MISSING})
- Acompanante: [Acompanante] ({OMIT_IF_MISSING})
- Clasificacion de triage: [Clasificacion de triage] ({OMIT_IF_MISSING})
- Motivo de consulta: [Motivo de consulta] ({OMIT_IF_MISSING})

## Enfermedad actual
[Enfermedad actual en urgencias] ({OMIT_IF_MISSING} Priorizar tiempo de evolucion, sintoma principal, severidad, sintomas de alarma, manejo previo, antecedentes criticos, medicamentos y alergias relevantes.)

## Evaluacion inicial
- Estado general: [Estado general] ({OMIT_IF_MISSING})
- Estado de conciencia: [Estado de conciencia] ({OMIT_IF_MISSING})
- Via aerea: [Via aerea] ({OMIT_IF_MISSING})
- Respiracion: [Respiracion] ({OMIT_IF_MISSING})
- Circulacion: [Circulacion] ({OMIT_IF_MISSING})
- Deficit neurologico: [Deficit neurologico] ({OMIT_IF_MISSING})
- Exposicion / otros hallazgos: [Exposicion u otros hallazgos] ({OMIT_IF_MISSING})
- Signos vitales iniciales: [Signos vitales iniciales] ({OMIT_IF_MISSING})

## Examen fisico dirigido
- Cardiovascular: [Examen cardiovascular] ({OMIT_IF_MISSING})
- Respiratorio: [Examen respiratorio] ({OMIT_IF_MISSING})
- Abdomen: [Examen abdominal] ({OMIT_IF_MISSING})
- Neurologico: [Examen neurologico] ({OMIT_IF_MISSING})
- Osteomuscular / trauma: [Examen osteomuscular o trauma] ({OMIT_IF_MISSING})
- Piel y mucosas: [Piel y mucosas] ({OMIT_IF_MISSING})
- Otros sistemas relevantes: [Otros sistemas relevantes] ({OMIT_IF_MISSING})

## Impresion diagnostica
- Diagnostico principal: [Diagnostico principal] ({OMIT_IF_MISSING})
- Diagnosticos diferenciales: [Diagnosticos diferenciales] ({OMIT_IF_MISSING})
- Riesgo clinico percibido: [Riesgo clinico percibido] ({OMIT_IF_MISSING})

## Manejo en urgencias
- Medidas iniciales: [Medidas iniciales] ({OMIT_IF_MISSING})
- Medicamentos administrados: [Medicamentos administrados] ({OMIT_IF_MISSING})
- Liquidos / oxigeno / monitorizacion: [Soporte con liquidos, oxigeno o monitorizacion] ({OMIT_IF_MISSING})
- Examenes solicitados: [Examenes solicitados] ({OMIT_IF_MISSING})
- Imagenes solicitadas: [Imagenes solicitadas] ({OMIT_IF_MISSING})
- Procedimientos realizados: [Procedimientos realizados] ({OMIT_IF_MISSING})
- Interconsultas: [Interconsultas] ({OMIT_IF_MISSING})
- Respuesta al manejo: [Respuesta al manejo] ({OMIT_IF_MISSING})

## Evolucion en urgencias
[Evolucion durante la estancia en urgencias] ({OMIT_IF_MISSING})

## Conducta final
- Alta: [Alta] ({OMIT_IF_MISSING})
- Observacion: [Observacion] ({OMIT_IF_MISSING})
- Hospitalizacion: [Hospitalizacion] ({OMIT_IF_MISSING})
- Remision / referencia: [Remision o referencia] ({OMIT_IF_MISSING})
- Recomendaciones de egreso: [Recomendaciones de egreso] ({OMIT_IF_MISSING})
- Signos de alarma: [Signos de alarma] ({OMIT_IF_MISSING})
- Formula medica: [Formula medica] ({OMIT_IF_MISSING})
- Incapacidad: [Incapacidad] ({OMIT_IF_MISSING})
- Control: [Control] ({OMIT_IF_MISSING})

## Cierre
- Condicion al egreso o traslado: [Condicion al egreso o traslado] ({OMIT_IF_MISSING})
- Profesional responsable: [Profesional responsable] ({OMIT_IF_MISSING})
""".strip(),
    },
    {
        "name": "Ingreso hospitalario",
        "document_kind": "document",
        "content": f"""
{COMMON_HEADER}

## Encabezado
- Tipo de documento: Ingreso hospitalario
- Fecha y hora de ingreso: [Fecha y hora de ingreso] ({OMIT_IF_MISSING})
- Servicio: [Servicio] ({OMIT_IF_MISSING})
- Procedencia: [Procedencia] ({OMIT_IF_MISSING})
- Motivo de hospitalizacion: [Motivo de hospitalizacion] ({OMIT_IF_MISSING})

## Resumen del caso
[Resumen del caso] ({OMIT_IF_MISSING} Escribir como parrafo clinico breve.)

## Enfermedad actual
[Enfermedad actual de hospitalizacion] ({OMIT_IF_MISSING})

## Antecedentes relevantes
- Patologicos: [Antecedentes patologicos] ({OMIT_IF_MISSING})
- Quirurgicos: [Antecedentes quirurgicos] ({OMIT_IF_MISSING})
- Alergicos: [Alergias] ({OMIT_IF_MISSING})
- Farmacologicos: [Medicamentos actuales] ({OMIT_IF_MISSING})
- Familiares: [Antecedentes familiares] ({OMIT_IF_MISSING})
- Otros: [Otros antecedentes] ({OMIT_IF_MISSING})

## Evaluacion clinica de ingreso
- Signos vitales: [Signos vitales] ({OMIT_IF_MISSING})
- Estado general: [Estado general] ({OMIT_IF_MISSING})
- Examen fisico completo: [Examen fisico completo] ({OMIT_IF_MISSING})
- Escalas clinicas aplicables: [Escalas clinicas aplicables] ({OMIT_IF_MISSING})
- Riesgos identificados: [Riesgos identificados] ({OMIT_IF_MISSING})

## Paraclinicos e imagenes disponibles
[Paraclinicos e imagenes disponibles] ({OMIT_IF_MISSING})

## Analisis
[Analisis de hospitalizacion] ({OMIT_IF_MISSING})

## Diagnosticos de ingreso
- Diagnostico principal: [Diagnostico principal de ingreso y codigo si fue mencionado] ({OMIT_IF_MISSING})
- Diagnosticos relacionados: [Diagnosticos relacionados] ({OMIT_IF_MISSING})
- Diagnosticos diferenciales: [Diagnosticos diferenciales] ({OMIT_IF_MISSING})

## Plan intrahospitalario
- Ubicacion / nivel de cuidado: [Nivel de cuidado] ({OMIT_IF_MISSING})
- Monitorizacion: [Monitorizacion] ({OMIT_IF_MISSING})
- Medicamentos: [Medicamentos] ({OMIT_IF_MISSING})
- Liquidos y nutricion: [Liquidos y nutricion] ({OMIT_IF_MISSING})
- Oxigeno / soporte respiratorio: [Soporte respiratorio] ({OMIT_IF_MISSING})
- Examenes de control: [Examenes de control] ({OMIT_IF_MISSING})
- Interconsultas: [Interconsultas] ({OMIT_IF_MISSING})
- Procedimientos previstos: [Procedimientos previstos] ({OMIT_IF_MISSING})
- Profilaxis / prevencion de riesgos: [Profilaxis o prevencion de riesgos] ({OMIT_IF_MISSING})
- Educacion a paciente y familia: [Educacion a paciente y familia] ({OMIT_IF_MISSING})
- Criterios de alarma intrahospitalaria: [Criterios de alarma intrahospitalaria] ({OMIT_IF_MISSING})

## Cierre
- Paciente y/o familia informados: [Paciente y/o familia informados] ({OMIT_IF_MISSING})
- Profesional responsable: [Profesional responsable] ({OMIT_IF_MISSING})
""".strip(),
    },
    {
        "name": "Epicrisis o resumen de egreso",
        "document_kind": "document",
        "content": f"""
{COMMON_HEADER}

## Identificacion del episodio
- Fecha de ingreso: [Fecha de ingreso] ({OMIT_IF_MISSING})
- Fecha de egreso: [Fecha de egreso] ({OMIT_IF_MISSING})
- Servicio responsable: [Servicio responsable] ({OMIT_IF_MISSING})
- Dias de estancia: [Dias de estancia] ({OMIT_IF_MISSING})
- Motivo de ingreso: [Motivo de ingreso] ({OMIT_IF_MISSING})
- Condicion al egreso: [Condicion al egreso] ({OMIT_IF_MISSING})

## Diagnosticos
- Diagnostico principal de egreso: [Diagnostico principal de egreso y codigo si fue mencionado] ({OMIT_IF_MISSING})
- Diagnosticos secundarios: [Diagnosticos secundarios] ({OMIT_IF_MISSING})
- Complicaciones: [Complicaciones] ({OMIT_IF_MISSING})
- Causa externa: [Causa externa] ({OMIT_IF_MISSING})

## Resumen de hospitalizacion
[Resumen de hospitalizacion] ({OMIT_IF_MISSING} Incluir hallazgos relevantes al ingreso, evolucion clinica, resultados importantes, procedimientos, interconsultas y respuesta al tratamiento cuando esten mencionados.)

## Tratamiento recibido
- Medicamentos intrahospitalarios principales: [Medicamentos intrahospitalarios principales] ({OMIT_IF_MISSING})
- Procedimientos / terapias: [Procedimientos o terapias] ({OMIT_IF_MISSING})
- Cambios relevantes durante la estancia: [Cambios relevantes durante la estancia] ({OMIT_IF_MISSING})

## Plan de egreso
- Medicamentos al egreso: [Medicamentos al egreso] ({OMIT_IF_MISSING})
- Recomendaciones generales: [Recomendaciones generales] ({OMIT_IF_MISSING})
- Dieta / actividad / cuidados: [Dieta, actividad y cuidados] ({OMIT_IF_MISSING})
- Citas de control: [Citas de control] ({OMIT_IF_MISSING})
- Examenes pendientes: [Examenes pendientes] ({OMIT_IF_MISSING})
- Remisiones: [Remisiones] ({OMIT_IF_MISSING})
- Signos de alarma: [Signos de alarma] ({OMIT_IF_MISSING})
- Incapacidad medica: [Incapacidad medica] ({OMIT_IF_MISSING})
- Educacion brindada: [Educacion brindada] ({OMIT_IF_MISSING})

## Cierre
- Paciente y/o cuidador comprende indicaciones: [Comprension de indicaciones por paciente o cuidador] ({OMIT_IF_MISSING})
- Profesional responsable del egreso: [Profesional responsable del egreso] ({OMIT_IF_MISSING})
""".strip(),
    },
    {
        "name": "Nota de procedimiento",
        "document_kind": "document",
        "content": f"""
{COMMON_HEADER}

## Encabezado
- Tipo de documento: Nota de procedimiento
- Procedimiento realizado: [Procedimiento realizado] ({OMIT_IF_MISSING})
- Fecha y hora: [Fecha y hora] ({OMIT_IF_MISSING})
- Indicacion: [Indicacion] ({OMIT_IF_MISSING})
- Diagnostico relacionado: [Diagnostico relacionado] ({OMIT_IF_MISSING})
- Profesional que realiza: [Profesional que realiza] ({OMIT_IF_MISSING})
- Asistentes: [Asistentes] ({OMIT_IF_MISSING})

## Consentimiento y verificacion
- Consentimiento informado: [Consentimiento informado] ({OMIT_IF_MISSING})
- Riesgos explicados: [Riesgos explicados] ({OMIT_IF_MISSING})
- Sitio / lateralidad verificada: [Sitio o lateralidad verificada] ({OMIT_IF_MISSING})
- Lista de chequeo aplicada: [Lista de chequeo aplicada] ({OMIT_IF_MISSING})

## Descripcion del procedimiento
[Descripcion del procedimiento] ({OMIT_IF_MISSING} Incluir tecnica, anestesia o analgesia, insumos, hallazgos, muestras tomadas, complicaciones y tolerancia del paciente cuando esten mencionados.)

## Conducta posterior
- Cuidados posteriores: [Cuidados posteriores] ({OMIT_IF_MISSING})
- Medicamentos indicados: [Medicamentos indicados] ({OMIT_IF_MISSING})
- Recomendaciones: [Recomendaciones] ({OMIT_IF_MISSING})
- Signos de alarma: [Signos de alarma] ({OMIT_IF_MISSING})
- Control: [Control] ({OMIT_IF_MISSING})

## Cierre
- Estado final del paciente: [Estado final del paciente] ({OMIT_IF_MISSING})
- Profesional responsable: [Profesional responsable] ({OMIT_IF_MISSING})
""".strip(),
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
