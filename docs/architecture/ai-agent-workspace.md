# Arquitectura del Agente de IA (Medical Workspace Copilot)

## 1. Visión General

El Copiloto Clínico no es un servicio monolítico frontend. Responde a una arquitectura de **capas segregadas** diseñada para operar bajo normativas HIPAA, reducir latencia, minimizar el costo de tokens (Context Caching) y garantizar cero escrituras fantasmas o alucinaciones destructivas.

### Componentes Principales

1. **Frontend (React / Vite):**
   - **Responsabilidad:** Renderizado visual (Lexical), estado del workspace (`WorkspaceStore`, `DocumentSnapshotStore`, `DocumentDraftStore`, `DocumentDerivedStore`), UI del chat futura y revisión de parches.
   - **Restricción:** No posee lógica del LLM, no gestiona el contexto clínico completo, no almacena keys, no consolida documentos pesados directamente desde componentes.
   - **Slice actual:** el primer consumidor del broker es un debug panel interno en `EncuentroDetail`, y hoy ya valida `proposal + review + safe apply`, no la UX final del copiloto.

2. **Backend Transaccional (Django / Cloud Run):**
   - **Responsabilidad:** Fuente única de la verdad. Persistencia de `documents`, `snapshots`, seguridad, permisos y servicios de API.
   - **Boundary adicional:** actúa como broker seguro entre frontend y `copilot-agent-service` con endpoints `sessions / messages / runs / stream`.
   - **Estado actual del writer flow:** persiste `CopilotPatchSet` + `CopilotPatch`, resuelve anchors a rangos reales, detecta conflictos internos y aplica solo cambios aceptados.

3. **Agent Runtime (LangGraph / Cloud Run):**
   - **Responsabilidad:** Orquestación, memoria de sesión, toma de decisiones (Tools) y generación de respuestas/patches.
   - **Boundary:** no es público al navegador; Django consume sus contratos internos.
   - **Estado actual:** usa PostgreSQL como checkpointer, persiste `runs`/`events`, lee documentos/contexto reales desde Django y ya corre con `ToolNode` + tool calling nativo de LangChain sobre Gemini/Vertex (`ChatGoogleGenerativeAI`). El planner mantiene mensajes LangChain reales y renderiza el contexto por turno con bloques XML, mientras el drafter usa `json_schema` structured output para construir `patch_set_preview` de un solo documento target. El `safe apply` final sigue en Django. El `thread_id` público identifica la conversación activa del sidechat y LangGraph lo usa directamente como checkpoint key para conservar contexto entre mensajes del mismo chat. Aunque usemos function/tool calling nativo, el runtime desactiva `Automatic Function Calling` del SDK de Google para que la orquestación siga ocurriendo dentro de LangGraph y no en el proveedor; en patch drafting no hay fallback a `function_calling`. El planner y el drafter tratan transcripciones, notas, spans y facts recuperados como datos clinicos, no como instrucciones ejecutables.

---

## 2. Flujo de Datos y Optimización de LLMs

Para resolver el problema de contexto masivo (ej. transcripciones de 30 minutos = ~15k tokens) sin quebrar latencia ni presupuesto, empleamos **Context Caching** junto con lecturas progresivas:

### Patrón "Index First"

- El Frontend nunca sube archivos largos en los payloads de chat.
- El Frontend expone un `WorkspaceIndex` ligero construido desde el workspace state layer, no desde JSX o estado local del editor.
- Ese `WorkspaceIndex` contiene metadatos como documento activo, `version`, `hasDirtyDraft`, `hasStreamingState`, `aiReadable` y working set.
- Django entrega ese `WorkspaceIndex` al agent runtime.
- El Agente usa el `WorkspaceIndex` para decidir qué leer y luego llama a tools internas read-only para obtener documentos y contexto reales desde Django.
- El broker Django persiste `CopilotRun`, consulta el estado del runtime y reemite SSE al frontend.
- En el sidechat actual, Django crea un `thread_id` nuevo por conversación; el frontend lo conserva solo en memoria del panel y lo reusa en mensajes siguientes hasta resetear el chat.

### Regla del frontend actual

- `contexts/` orquestan SSE, kickoff y compatibilidad.
- `workspace/` es el owner de tabs, snapshot, draft, derived state y preparación de patch review.
- El editor resuelve `derived > draft > snapshot`.
- El runtime futuro no debe leer markdown pesado desde componentes; debe leer el `WorkspaceIndex` y luego pedir contenido por herramientas.

### Boundary de red recomendado

- `frontend -> Django`
- `Django -> copilot-agent-service`
- `copilot-agent-service -> Django tools/contracts internos`
- `resolve target -> patch set proposal -> persisted patch set -> review granular -> safe apply -> resume`
- En writer flows, un run de edición solo es válido si termina en `waiting_review` con un `patch_set_preview` persistible o en `failed`; `patch_set_proposed + completed` se trata como inconsistencia del runtime.

El frontend no habla directo con LangGraph.

### Context Caching (Vertex AI / Gemini)

- **El Problema:** Leer una transcripción en 10 interacciones de chat costaría 150,000 tokens de input.
- **La Solución objetivo:** cuando exista un corpus estable y pesado reutilizable entre varias preguntas, el sistema puede crear un **Context Cache** explicito.
- En el slice actual del `document helper`, el runtime no usa explicit caching; depende del patrón `index first`, lecturas progresivas y continuidad del chat.
- La decisión de introducir explicit caching futuro para QA longitudinal o documentos pesados queda registrada en la deuda técnica y en ADR dedicada, no como comportamiento actual del writer flow.

---

## 3. Políticas de Lectura y Escritura (Safety)

### Lectura Longitudinal vs. Activa

- **Encuentro Actual:** El runtime usa `index first` y lecturas progresivas desde Django para leer la transcripción y el contexto real del encounter dentro del mismo chat; no depende hoy de explicit caching para el `document helper`.
- **Historia Clínica Pasada:** Jamás se envían decenas de audios crudos al agente. El Agente usa herramientas de resumen (`mode: summary`) sobre la tabla de metadatos/resúmenes derivados en PostgreSQL `document_summaries`.

### El Sistema de Patches (Escritura Segura)

El agente de IA **tiene prohibido escribir o sobreescribir** el contenido canónico directamente (Snapshot).

1. El Agente genera un `patch_set_preview` con cambios pequeños y anclados para un solo documento target.
   - La descomposición semántica del pedido vive en el LLM drafter.
   - El runtime de producción ya no usa fallback heurístico para decidir tools ni para redactar cambios.
   - El loop principal usa tool calling nativo (`AIMessage.tool_calls -> ToolNode -> ToolMessage`) y devuelve observaciones corregibles a la conversación cuando una tool falla o recibe un schema inválido.
   - Si Vertex falla o no materializa cambios reales, el writer flow falla cerrado en vez de abrir un review con placeholders.
2. Django resuelve anchors a rangos reales, persiste un `CopilotPatchSet` y marca cada `CopilotPatch` como `pending` o `conflicted`.
3. El frontend renderiza la propuesta desde el patch set y sus patches hijos.
4. El médico audita: acepta o rechaza cambios individuales, o el set completo.
5. Tras la aprobación final, Django aplica solo los patches aceptados sobre el documento canónico, invalida sets hermanos y el frontend sincroniza snapshot/draft/editor.

El debug panel y la futura UI lateral no dependen únicamente de la lista persistida de patches: si el stream ya emitió `patch_set_proposed` y el run está en `waiting_review`, el frontend puede derivar un estado efectivo temporal hasta que Django termine de reflejarlo en `GET /patch-sets`.

Lo que sigue pendiente ya no es el apply básico, sino el audit trail clínico fuerte, versionado robusto, rebase seguro sobre documentos cambiados y la UX final fuera del debug panel. La deuda canónica está en [`../debt/copilot-agent-runtime.md`](../debt/copilot-agent-runtime.md).

## 4. Checklist para Escalabilidad

- [x] **Fase actual:** Django ya brokeriza el flujo read-only y el runtime persiste `thread state` en PostgreSQL.
- [ ] **Fase Escalamiento (Múltiples Réplicas):** Reemplazar estados en memoria y pub/sub SSE hacia Redis (Google Cloud Memorystore) para evitar pérdida de streams entre contadores concurrentes.
- [ ] **Fase de Seguridad Operativa:** Migrar el broker `shared JWT` a OIDC/ID token service-to-service.
