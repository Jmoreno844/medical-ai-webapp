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

3. **Agent Runtime (LangGraph / Cloud Run):**
   - **Responsabilidad:** Orquestación, memoria de sesión, toma de decisiones (Tools) y generación de respuestas/patches.
   - **Boundary:** no es público al navegador; Django consume sus contratos internos.
   - **Estado actual:** usa PostgreSQL como checkpointer, persiste `runs`/`events`, lee documentos/contexto reales desde Django, resuelve documento objetivo por título/familia y ya puede proponer patches que pasan por `waiting_review` antes de un `safe apply` en Django.

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

### Regla del frontend actual

- `contexts/` orquestan SSE, kickoff y compatibilidad.
- `workspace/` es el owner de tabs, snapshot, draft, derived state y preparación de patch review.
- El editor resuelve `derived > draft > snapshot`.
- El runtime futuro no debe leer markdown pesado desde componentes; debe leer el `WorkspaceIndex` y luego pedir contenido por herramientas.

### Boundary de red recomendado

- `frontend -> Django`
- `Django -> copilot-agent-service`
- `copilot-agent-service -> Django tools/contracts internos`
- `resolve target -> proposal -> persisted patch -> review -> safe apply -> resume`
- En writer flows, un run de edición solo es válido si termina en `waiting_review` con un patch persistible o en `failed`; `patch_proposed + completed` se trata como inconsistencia del runtime.

El frontend no habla directo con LangGraph.

### Context Caching (Vertex AI / Gemini)

- **El Problema:** Leer una transcripción en 10 interacciones de chat costaría 150,000 tokens de input.
- **La Solución:** Cuando la transcripción del encuentro entra en un estado "estable", el Backend crea un **Context Cache**.
- El Agente invoca al LLM pasando simplemente el `cache_id` y el prompt variable del usuario (además de la nota). Esto proporciona ahorros superiores al 60% en input cost y drástica reducción de latencia (TTFT) manteniendo **100% de la precisión**.

---

## 3. Políticas de Lectura y Escritura (Safety)

### Lectura Longitudinal vs. Activa

- **Encuentro Actual:** Se lee la transcripción completa mediante Context Caching.
- **Historia Clínica Pasada:** Jamás se envían decenas de audios crudos al agente. El Agente usa herramientas de resumen (`mode: summary`) sobre la tabla de metadatos/resúmenes derivados en PostgreSQL `document_summaries`.

### El Sistema de Patches (Escritura Segura)

El agente de IA **tiene prohibido escribir o sobreescribir** el contenido canónico directamente (Snapshot).

1. El Agente genera un `DocumentPatch`.
2. El sistema lo guarda en BD como `pending`.
3. El frontend lo renderiza como previsualización de bloque.
4. El médico audita: Acepta, Modifica o Rechaza el parche.
5. Tras la aprobación, Django aplica el contenido propuesto sobre el documento canónico, actualiza el estado del patch y el frontend sincroniza snapshot/draft/editor.

El debug panel y la futura UI lateral no dependen únicamente de la lista persistida de patches: si el stream ya emitió `patch_proposed` y el run está en `waiting_review`, el frontend deriva un `effectivePendingPatch` hasta que Django termine de reflejarlo en `GET /patches`.

Lo que sigue pendiente ya no es el apply básico, sino el audit trail clínico fuerte, versionado robusto y la UX final fuera del debug panel. La deuda canónica está en [`../debt/copilot-agent-runtime.md`](../debt/copilot-agent-runtime.md).

## 4. Checklist para Escalabilidad

- [x] **Fase actual:** Django ya brokeriza el flujo read-only y el runtime persiste `thread state` en PostgreSQL.
- [ ] **Fase Escalamiento (Múltiples Réplicas):** Reemplazar estados en memoria y pub/sub SSE hacia Redis (Google Cloud Memorystore) para evitar pérdida de streams entre contadores concurrentes.
- [ ] **Fase de Seguridad Operativa:** Migrar el broker `shared JWT` a OIDC/ID token service-to-service.
