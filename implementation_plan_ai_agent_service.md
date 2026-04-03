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
- creación de `thread_id` por conversación del sidechat, con scope validable de `encounter + user`
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
- `thread_id` nuevo por conversación del sidechat, creado al iniciar chat y reenviado en mensajes posteriores
- panel interno de validación para `thread_id`, `run_id`, estado y stream SSE
- slice técnico de verificación antes de diseñar la UX final del copiloto

### Fase 3.6 — Read-only tools reales

- tools internas `copilot_agent -> Django` para listar documentos abiertos, leer documento, buscar y leer contexto del encounter
- el runtime deja de responder solo con `WorkspaceIndex`/excerpts y pasa a leer contenido real bajo control del backend
- el debug panel sigue siendo el consumidor frontend de validación, no la UX final
- los flujos regulatorios especializados y cualquier write path quedan fuera de este bloque

### Fase 4 — Patch proposal

- generar `patch_set_preview` persistido en Django como `CopilotPatchSet` + `CopilotPatch`
- `waiting_review` + `review_required` como estado público del run
- resolución determinística de anchors y detección de conflictos internos en Django
- review granular por patch y review bulk por patch set
- `resume` del run en el agent service solo después del `apply` o rechazo final del set
- estado actual: el runtime ya puede draftar varios patches anclados dentro de un mismo `patch_set_preview` para un solo documento target; la UI todavía mantiene compat temporal con una card legacy del primer patch

### Fase 5 — Safe apply

- backend aplica solo patches aceptados sobre `Document.content`
- el review devuelve metadata del documento aplicado para hidratar frontend sin reload
- invalidación/sincronización de `snapshot`, `draft` y preview local del editor
- invalidación de patch sets hermanos pendientes/aceptados sobre el mismo documento
- estado actual: implementado con `PatchSet`, anchors resueltos en Django, apply transaccional y targeting determinístico por título/familia de documento

### Fase 6 — Hardening del writer flow

- audit trail clínico completo del apply
- versionado fuerte del documento para conflictos y stale detection más robusta
- patch synthesis más precisa y fiable para prompts complejos de varios cambios, sin depender de parsing semántico heurístico en el fallback
- planner/tool loop migrado a tool calling nativo (`ChatGoogleGenerativeAI` + `ToolNode`) con mensajes LangChain reales y contexto XML por turno
- tools tipadas y auditables contra Django, con observaciones corregibles (`ToolMessage`) cuando una llamada falla
- structured output `json_schema` para `DraftedPatchPlan` y patch drafting sin `json.loads()` manual ni fallback a `function_calling`
- si el drafter no devuelve cambios materializados, el runtime debe fallar cerrado y no abrir una review con texto placeholder
- el planner del runtime ya no usa fallback heurístico de routing; si Vertex falla, el run debe cerrar en `failed` con error explícito
- guardrails para que un run de edición nunca termine en `completed` antes de `waiting_review`
- validación estricta de `tool_input` del planner y rechazo de runs inconsistentes desde Django
- derivación frontend de estado efectivo desde stream + persistencia, no solo desde la lista de patches
- UX de review multi-patch sobre `PatchSet` en vez del debug panel single-patch legacy
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
