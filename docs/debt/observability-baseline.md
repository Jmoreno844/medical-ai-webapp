# Deuda: baseline de observabilidad operativa para launch

## Estado

Aceptada temporalmente.

## Alcance

`backend_fastapi/`, `cloud_functions/`, `infra/modules/monitoring`, Cloud Run,
Cloud Functions, Cloud Tasks y Cloud SQL.

## Situacion actual

El repo ya tiene piezas utiles de observabilidad, pero no un baseline operativo
completo para launch:

- logs con `trace_id` / `span_id` en backend
- OpenTelemetry entre FastAPI y Cloud Functions cuando el export esta activo
- alertas Terraform para `Cloud Run 5xx`, `Cloud Function 5xx` y `Cloud SQL CPU`
- budget mensual en GCP

Eso ayuda a depurar fallos visibles, pero todavia deja huecos importantes para
operacion diaria. Hoy faltan, como minimo, metricas, alertas y dashboards para:

- latencia p95/p99 del backend y de la Cloud Function de generacion
- memoria y CPU de Cloud Run
- saturacion o backlog de Cloud Tasks
- errores por dominio (`transcription_error`, `generation_error`)
- caidas o desconexiones anormales de SSE
- conexiones, saturacion y almacenamiento de Cloud SQL
- canales reales de notificacion y runbooks de respuesta

## Impacto actual

- Un launch con transcripcion y generacion documental puede degradarse sin una
  senal temprana clara.
- El equipo podria enterarse por medicos o por soporte antes que por alertas.
- Un aumento de latencia, backlog de transcripcion o consumo de memoria podria
  parecer "la IA esta lenta" aunque el fallo real este en Cloud Tasks, Cloud
  SQL o Cloud Run.
- Las trazas actuales no cubren extremo a extremo SSE ni subida directa a GCS,
  por lo que la operacion necesita metricas agregadas y logs saneados, no solo
  spans.

## Por que se acepta temporalmente

- Antes del launch no-copilot la prioridad ha sido cerrar el flujo clinico
  principal y mantener la arquitectura simple.
- El producto va a salir con backend en una sola instancia por el hub SSE en
  memoria, lo que reduce parte de la complejidad inicial.
- Ya existe una base minima de logging, tracing y alertas; falta volverla
  operativamente util.

## Configuracion minima recomendada antes de launch

### Alertas

- Cloud Run backend: `5xx`, latencia p95, memoria alta, instancias saturadas.
- Cloud Function de generacion: `5xx`, duracion alta, ejecuciones fallidas.
- Cloud Tasks: cola en crecimiento, antiguedad de tarea alta, reintentos altos.
- Cloud SQL: CPU alta, conexiones altas, almacenamiento bajo.

### Dashboards

- Vista "backend clinico" con requests, latencia, memoria, CPU y errores.
- Vista "IA" con transcripciones iniciadas/completadas/fallidas, generaciones
  iniciadas/completadas/fallidas y duracion por flujo.
- Vista "datos" con CPU/conexiones de Cloud SQL y backlog de Cloud Tasks.

### Metricas y logs de dominio

- Contadores saneados por evento: `transcription_update`,
  `transcription_complete`, `generation_chunk`, `generation_complete`,
  `generation_error`.
- Logs estructurados por `document_id`, `encounter_id`, `process_id` y
  `trace_id`, sin contenido clinico completo.
- Log-based metrics para errores de transcripcion y generacion si no se
  exponen metricas de aplicacion propias.

### Operacion

- Conectar alertas a canales reales de notificacion, no dejarlas sin destino.
- Definir runbook corto por alerta: que mirar primero, quien responde, cuando
  escalar.
- Revisar retencion y saneamiento de logs para no filtrar PHI.

## Owner sugerido

- Infraestructura/operacion GCP: `infra/`
- Señales de dominio y logging sano: `backend_fastapi/` y `cloud_functions/`

## Trigger para pagarla

Esta deuda deja de ser aceptable cuando ocurra cualquiera de estas
condiciones:

- launch a medicos reales sin Copilot
- mas de 10 doctores concurrentes usando transcripcion o generacion
- incidentes donde el equipo no pueda distinguir rapido si el problema esta en
  backend, Cloud Function, Cloud Tasks o Cloud SQL
- decision de subir carga, concurrencia o replicas

## Referencias

- [`../architecture/system-overview.md`](../architecture/system-overview.md)
- [`../backend/tracing.md`](../backend/tracing.md)
- [`../backend/logging.md`](../backend/logging.md)
- [`../../infra/modules/monitoring/main.tf`](../../infra/modules/monitoring/main.tf)