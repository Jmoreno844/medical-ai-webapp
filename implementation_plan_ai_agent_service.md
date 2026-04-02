# Plan de Implementación — AI Agent Service

## Objetivo

Crear un runtime dedicado para el copiloto clínico fuera del backend principal,
desplegado como `copilot-agent-service` en Cloud Run y consumido por el
backend Django como broker seguro.

## Principios

1. El backend principal sigue siendo la autoridad transaccional y clínica.
2. El agent runtime no aplica cambios clínicos críticos por sí solo.
3. La escritura AI entra como `patch -> review -> apply`.
4. El frontend no habla directo con LangGraph; Django media el acceso.
5. El thread state del agente no vive en memoria del contenedor.

## Fases

### Fase 0 — Boundary y contratos

- cerrar ADR e infraestructura objetivo
- definir contratos internos `runs / resume / events / status`
- definir payload `WorkspaceIndex`
- definir `CopilotState`

### Fase 1 — Runtime dedicado

- scaffold del servicio `copilot_agent/`
- Docker local
- Cloud Run separado
- Cloud SQL con DB lógica separada
- workflow de deploy `stg`

### Fase 2 — Broker Django

- endpoints internos/públicos en Django
- mapping `encounter + user -> thread_id`
- validación de permisos antes de crear o reanudar runs
- relay de eventos al frontend
- `CopilotRun` persistido para reconnect y trazabilidad
- `shared JWT` temporal documentado como deuda canónica en `docs/debt/copilot-agent-runtime.md`

### Fase 3 — Read-only copilot

- responder preguntas
- seleccionar documentos del `WorkspaceIndex`
- leer contexto resumido
- no editar contenido todavía
- estado actual: implementado como primer slice brokered end-to-end

### Fase 3.5 — Frontend debug client

- cliente frontend pequeño contra el broker Django ya existente
- envío de `WorkspaceIndex` real desde el encounter detail
- panel interno de validación para `thread_id`, `run_id`, estado y stream SSE
- slice técnico de verificación antes de diseñar la UX final del copiloto

### Fase 3.6 — Read-only tools reales

- tools internas `copilot_agent -> Django` para listar documentos abiertos, leer documento, buscar y leer contexto del encounter
- el runtime deja de responder solo con `WorkspaceIndex`/excerpts y pasa a leer contenido real bajo control del backend
- el debug panel sigue siendo el consumidor frontend de validación, no la UX final
- los flujos regulatorios especializados y cualquier write path quedan fuera de este bloque

### Fase 4 — Patch proposal

- generar `patch_preview` persistido en Django como `CopilotPatch`
- `waiting_review` + `review_required` como estado público del run
- approve/reject desde Django y desde el debug panel lateral actual
- `resume` del run en el agent service sin `apply` real todavía

### Fase 5 — Safe apply

- backend aplica patch aprobado sobre `Document.content`
- el review devuelve metadata del documento aplicado para hidratar frontend sin reload
- invalidación/sincronización de `snapshot`, `draft` y preview local del editor
- estado actual: implementado con version check pragmático desde frontend, apply transaccional en Django y targeting determinístico por título/familia de documento

### Fase 6 — Hardening del writer flow

- audit trail clínico completo del apply
- versionado fuerte del documento para conflictos y stale detection más robusta
- patch synthesis más precisa que la reescritura full-document actual
- mover la experiencia desde debug panel hacia UX final del copiloto

## Infra y operación

- Cloud Run separado para el agent runtime
- misma instancia Cloud SQL al inicio, DB separada
- SA dedicada con `cloudsql.client`, `cloudsql.instanceUser`,
  `aiplatform.user`, `cloudtrace.agent`
- sin Redis en v1
- sin Agent Server oficial en v1

## Local dev

- `backend/docker-compose.yml`
- `cloud_functions/docker-compose.yml`
- `copilot_agent/docker-compose.yml`
- misma máquina, servicios separados

## Definition of done del servicio

- healthcheck local
- create run / resume / status / events funcionales
- documentación de boundary y contratos actualizada
- Terraform `stg` listo para un segundo Cloud Run
- workflow de deploy separado

## Qué falta después de este slice

- consumo frontend real más allá del debug panel técnico
- audit trail clínico completo del apply
- versionado fuerte del documento para conflictos y merges seguros
- herramientas más profundas del agent runtime contra backend y dominio clínico, una vez estabilizado el set inicial de proposal + review
- migración de `shared JWT` a OIDC o ID token service-to-service
- decisión final de UX del copiloto lateral
