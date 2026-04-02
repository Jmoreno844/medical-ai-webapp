# Plan Maestro de Implementación — AI Medical Workspace Helper

## Objetivo

Convertir el editor actual en un **workspace clínico multi-documento AI-ready** sin romper velocidad de desarrollo, sin sobrecargar la base de datos con micro-lecturas innecesarias, y sin volver rígido el sistema alrededor de tipos fijos de nota.

Este plan asume:

- frontend React web
- editor actual con Lexical
- tabs para transcripción, contexto y documentos extra
- copiloto lateral / AI agent
- necesidad futura de sugerencias, revisión, aceptación/rechazo, MIPRES draft y copy por partes hacia EHRs
- un solo developer, por lo que la estrategia debe ser incremental, con hitos claros y evitando refactors suicidas

---

# Principio central

**No construir primero “el agente completo”.**

Primero hay que construir el **suelo firme** sobre el que el agente pueda trabajar bien:

1. contratos de documentos
2. snapshots y drafts separados
3. lectura eficiente del workspace
4. operaciones / patches
5. review layer

Solo después conviene subir el nivel del agente.

Si se hace al revés, el agente terminará acoplado a:

- strings grandes de markdown
- tabs tratadas como views sueltas
- lecturas completas innecesarias
- writes directos al contenido final
- lógica poco trazable

---

# Decisión importante sobre secciones

## No usar `ClinicalSection` rígido por tipo de nota

Tu preocupación es válida: en la práctica clínica, la estructura depende muchísimo del médico, la especialidad, el tipo de encuentro, la costumbre local e incluso del EHR destino. Si fuerzas demasiado temprano un esquema fijo como:

- motivo de consulta
- enfermedad actual
- antecedentes
- examen físico
- análisis
- plan

te arriesgas a que:

- el producto se sienta artificial
- el médico pierda flexibilidad
- muchas notas “válidas” queden mal modeladas
- el agente se confunda más cuando la estructura real no coincida con la esperada

## Reemplazo recomendado: secciones flexibles + etiquetas opcionales

La arquitectura no debe exigir un tipo fijo de nota. En vez de eso, usa una capa flexible:

```ts
export type SectionSemanticTag =
  | "subjective"
  | "objective"
  | "assessment"
  | "plan"
  | "history"
  | "medications"
  | "diagnosis"
  | "orders"
  | "recommendations"
  | "other";

export type DocumentSection = {
  id: string;
  title: string;
  contentMarkdown: string;
  order: number;
  semanticTag?: SectionSemanticTag;
  userDefined: boolean;
  aiWritable: boolean;
  copyable: boolean;
};
```

### Qué ganas con esto

- el médico puede tener títulos libres
- sigues pudiendo copiar por sección
- el agente puede editar por bloque
- puedes mapear algunas secciones a semánticas conocidas sin imponerlas
- más adelante puedes tener plantillas por especialidad sin que el core dependa de ellas

### Regla

- la **UI** y el **modelo persistido** trabajan con secciones flexibles
- la **capa semántica** puede sugerir tags o equivalencias, pero no imponerlas como requisito

---

# Puente con el repo actual

Antes de hablar de `WorkspaceStore`, `DocumentSnapshot` o `DocumentPatch`, hay que reconocer cómo funciona hoy el producto para no diseñar una migración imaginaria.

## Estado actual relevante

Hoy el flujo real del encounter detail ya tiene una base útil:

- `WorkspaceStore` ya es dueño de tabs y documento activo
- `ContentContext` ya opera como bridge sobre `DocumentSnapshotStore` + `DocumentDraftStore`
- `DocumentDerivedStore` ya empezó a absorber streaming y modo del editor
- `GenerationContext` y `TranscriptionContext` siguen siendo dueños del lifecycle SSE y side effects largos
- `Lexical` renderiza y edita, pero no debería consolidarse como fuente de verdad
- el backend actual sigue teniendo `documents.content` como contenido canónico persistido

## Dónde está la tensión hoy

La implementación actual todavía mezcla varias capas que este plan quiere separar mejor:

- contenido persistido del documento
- cache de lectura del documento
- draft local del editor
- contenido derivado de streaming
- estado visual interno de Lexical

Ese solapamiento no invalida la base actual, pero sí significa que la transición debe ser **evolutiva** y no una reescritura.

## Regla de migración

No romper de una sola vez:

- tabs
- autosave
- streaming de generación
- transcripción
- contratos backend existentes

La transición correcta es:

1. introducir el nuevo lenguaje (`snapshot`, `draft`, `derived`, `patch`)
2. mapearlo sobre la implementación actual
3. mover responsabilidades poco a poco
4. recién después cambiar persistencia o contratos

## Mapeo inicial recomendado

- `DocumentContext` -> primer candidato a `WorkspaceStore` en Zustand
- `ContentContext` -> primer candidato a `DocumentSnapshotStore` + `DocumentDraftStore`
- `GenerationContext` -> primer candidato a `DocumentDerivedStore`
- `TranscriptionContext` -> flujo especializado read-only conectado a stores del workspace
- `Lexical` -> vista/edición del draft actual

### Estado de avance real del repo

- `Plan 1-2`: base de `Zustand`, `WorkspaceStore` y bridge de `DocumentContext` ya aterrizados
- `Plan 3`: `snapshot + draft` y parte de la integración con `Lexical` ya aterrizados
- siguiente prioridad práctica: cerrar ownership de `derived`, `WorkspaceIndex`, `AiSessionStore` y `PatchStore` antes de abrir el runtime del agente

Este mapeo es importante porque permite avanzar sin exigir una migración total en el primer slice.

---

# Qué hacer primero

## Orden recomendado realista

### Fase 0 — Contratos y modelo mental

Primero define el lenguaje del sistema.

### Fase 1 — Refactor base del frontend

Separar workspace, snapshots, drafts y derived state.

### Fase 2 — Capa de lectura AI-ready

Crear el índice del workspace y la lectura progresiva.

### Fase 3 — Agente read-only

Primero que lea bien, resuma bien y navegue bien.

### Fase 4 — Patches y review

Introducir cambios sugeridos sin writes directos.

### Fase 5 — Agente con escritura supervisada

Solo después de tener patches y revisión.

### Fase 6 — MIPRES / docs estructurados / optimizaciones

Lo más específico después.

## Qué NO recomiendo

No recomiendo este orden:

1. terminar “todo el frontend” primero
2. luego hacer el agente completo al final

porque normalmente termina en que:

- el frontend queda pensado para usuario humano, no para agente
- el agente obliga a reabrir todas las decisiones de estado
- todo se vuelve doble trabajo

Tampoco recomiendo:

1. construir el agente ya mismo
2. dejar que lea tabs y markdown bruto
3. improvisar writes después

porque eso te amarra a un diseño débil.

## Estrategia correcta

Haz **vertical slices**, pero con base arquitectónica primero:

- slice 1: documentos y snapshots
- slice 2: lectura AI del workspace
- slice 3: agente read-only útil
- slice 4: sugerencias con patches
- slice 5: agente writer supervisado

---

# Arquitectura objetivo

## Vista general

```text
React UI / Lexical
    ↓
Workspace State Layer
    ↓
Document Snapshot / Draft / Patch Layer
    ↓
AI Context Resolver + Agent Tools
    ↓
API / Backend Services
    ↓
Persistence (documents, versions, summaries, patches, audit)
```

## Regla madre

**Lexical no es la fuente de verdad.**

Lexical es:

- editor visual
- selección
- UX de edición
- shortcuts
- formato
- serialización visual

La fuente de verdad debe ser:

- documento tipado
- snapshot persistido
- draft local
- patches pendientes / aplicados
- resolver de contexto AI

---

# Modelo de datos recomendado

## 1. WorkspaceDocument

```ts
export type WorkspaceDocumentType =
  | "note"
  | "transcription"
  | "context"
  | "uploaded_document"
  | "generated_document"
  | "mipres_draft"
  | "patient_history_summary";

export type WorkspaceDocumentStatus =
  | "draft"
  | "streaming"
  | "suggested"
  | "reviewed"
  | "final"
  | "read_only";

export type WorkspaceDocument = {
  id: string;
  encounterId: string;
  type: WorkspaceDocumentType;
  title: string;
  status: WorkspaceDocumentStatus;
  source: "user" | "transcription" | "ai" | "external" | "system";

  aiReadable: boolean;
  aiWritable: boolean;
  userEditable: boolean;

  version: number;
  contentMarkdown: string;
  metadata: Record<string, unknown>;

  summaryShort?: string;
  summaryClinical?: string;
  contentHash?: string;
  estimatedTokens?: number;

  createdAt: string;
  updatedAt: string;
};
```

## 2. DocumentSnapshot

```ts
export type DocumentSnapshot = {
  documentId: string;
  version: number;
  contentMarkdown: string;
  lexicalJson?: unknown;
  sections?: DocumentSection[];
  savedAt: string;
};
```

## 3. DocumentDraftState

```ts
export type DocumentDraftState = {
  documentId: string;
  localUnsavedContent: string | null;
  localSections?: DocumentSection[];
  isDirty: boolean;
  lastEditedAt?: string;
};
```

## 4. DocumentDerivedState

```ts
export type DocumentDerivedState = {
  documentId: string;
  streamingContent?: string;
  patchPreviewContent?: string;
  regeneratedSummary?: string;
};
```

## 5. DocumentPatch

```ts
export type DocumentPatchOperationType =
  | "append_text"
  | "replace_range"
  | "replace_section"
  | "insert_after_section"
  | "create_document"
  | "update_title";

export type DocumentPatchStatus =
  | "pending"
  | "accepted"
  | "rejected"
  | "applied"
  | "stale";

export type DocumentPatch = {
  id: string;
  documentId: string;
  documentVersionBase: number;
  createdBy: "ai" | "user" | "system";
  sourceContextDocumentIds: string[];
  operationType: DocumentPatchOperationType;

  summary: string;
  rationale?: string;

  targetSectionId?: string;
  beforeContent?: string;
  afterContent: string;

  status: DocumentPatchStatus;
  createdAt: string;
  acceptedAt?: string;
  rejectedAt?: string;
};
```

## 6. PatchAudit

```ts
export type PatchAudit = {
  patchId: string;
  documentId: string;
  acceptedByUserId?: string;
  sourceDocumentIds: string[];
  agentTaskType: string;
  createdAt: string;
  acceptedAt?: string;
  rejectedAt?: string;
};
```

---

# Frontend state architecture recomendada

## Stores o contexts

No necesitas 20 contexts. Necesitas pocos, claros y con responsabilidad fuerte.

## Postura sobre Zustand

`Zustand` **sí lo recomiendo desde el inicio** para la nueva arquitectura del workspace.

### Recomendación actual

- Usar `Zustand` como base del nuevo `workspace state layer`
- Modelar desde el principio `snapshot`, `draft`, `derived`, `patch` y `ai session` como stores separados
- Mantener `Lexical` como vista y composición
- Mantener wrappers de providers solo cuando ayuden a bootstrapping, scoping o integración, pero no como dueño principal del estado del workspace

### Por qué sí lo pondría ya como decisión arquitectónica

- el producto va hacia múltiples capas de estado transversal: tabs, drafts, snapshots, patch review, AI side panel, working set, selection, streaming y permisos
- `Zustand` permite selectors finos y suscripciones pequeñas, algo muy útil cuando el editor, el panel AI y la barra de tabs viven al mismo tiempo
- para agentes y futuros chats, un set pequeño de stores bien nombrados suele ser más fácil de inspeccionar que un árbol de providers cada vez más profundo
- te deja crecer hacia flujos de review, patch previews y AI session state sin tener que reabrir otra vez la decisión de state management

### Qué no significa esta decisión

- no significa un store global gigantesco
- no significa mover toda la lógica del dominio a una sola carpeta `store`
- no significa esconder networking y SSE en acciones opacas sin contrato
- no significa reemplazar todos los boundaries del dominio por estado global

### Cómo usar Zustand bien en este caso

La recomendación no es “usar Zustand para todo”, sino usarlo **hasta donde realmente aporta**.

#### Sí usar Zustand para:

- **sí** para workspace shell state: tabs abiertas, documento activo, panel AI, working set, UI cross-cutting
- **sí** para snapshots canónicos cacheados por `documentId/version`
- **sí** para drafts locales, dirty state y autosave coordination
- **sí** para derived state de streaming, patch previews y summaries regenerados
- **sí** para patch/review queue y AI session state

#### No usar Zustand para:

- **no** como reemplazo del backend ni de la fuente de verdad persistida
- **no** como contenedor gigante para todo el sistema
- **no** para mezclar en el mismo store documentos, chat, auth, UI global y networking sin límites
- **no** para esconder side effects críticos sin ownership claro

### Regla de diseño

Usar varios stores pequeños y explícitos:

- el store guarda estado derivable y seleccionable
- los efectos complejos viven en acciones claras o servicios de dominio, no dispersos por componentes
- los stores exponen selectors de lectura y acciones de escritura con intención clara
- el editor no depende de “magia global” difícil de rastrear
- cada store debe tener owner, contrato y tests

## Recomendación concreta

Para este roadmap:

1. **Sí adoptar Zustand desde el inicio del refactor del workspace**
2. Empezar por `WorkspaceStore`, `DocumentSnapshotStore`, `DocumentDraftStore`, `DocumentDerivedStore`, `PatchStore` y `AiSessionStore`
3. Mantener una capa adaptadora temporal con los contexts actuales mientras se migra la UI
4. Retirar providers viejos solo cuando las rutas activas ya dependan del nuevo state layer

## A. WorkspaceStore

Responsabilidad:

- lista de documentos
- tabs abiertas
- documento activo
- orden de tabs
- permisos y visibilidad al copiloto

```ts
export type WorkspaceStoreState = {
  documentsById: Record<string, WorkspaceDocument>;
  openDocumentIds: string[];
  activeDocumentId: string | null;
  pinnedDocumentIds: string[];
  hiddenFromAgentDocumentIds: string[];
};
```

## B. DocumentSnapshotStore

Responsabilidad:

- snapshots persistidos o canónicos
- cache por documentId/version
- refresh desde backend

## C. DocumentDraftStore

Responsabilidad:

- contenido local no guardado
- dirty state
- autosave del usuario

## D. PatchStore

Responsabilidad:

- patches pendientes
- preview de cambios
- accept/reject/apply

## E. AiSessionStore

Responsabilidad:

- estado de la sesión actual del agent
- working set
- tool results recientes
- streaming de respuesta del chat
- estado de generación/sugerencia

---

# Capa AI-ready — la pieza que más importa

## Objetivo

Que el agente **no lea tabs del DOM**, **no lea todo upfront** y **no haga mini-calls inútiles**.

## 1. WorkspaceIndex

El primer payload del agente debe ser pequeño:

```ts
export type WorkspaceIndex = {
  encounterId: string;
  activeDocumentId: string | null;
  openDocumentIds: string[];
  documents: Array<{
    id: string;
    type: WorkspaceDocumentType;
    title: string;
    status: WorkspaceDocumentStatus;
    aiReadable: boolean;
    aiWritable: boolean;
    version: number;
    updatedAt: string;
    excerpt?: string;
    shortSummary?: string;
    estimatedTokens?: number;
    dirty?: boolean;
    hasPendingPatches?: boolean;
  }>;
};
```

## 2. Read modes

Nunca le des una sola herramienta de `readFullDocument()` como default.

```ts
export type ReadMode = "index" | "summary" | "sections" | "range" | "full";
```

## 3. Agent tools recomendadas

```ts
interface AgentWorkspaceTools {
  listWorkspaceDocuments(): Promise<WorkspaceIndex>;

  readDocuments(input: {
    items: Array<{
      documentId: string;
      mode: ReadMode;
      sectionIds?: string[];
      fromChar?: number;
      toChar?: number;
    }>;
  }): Promise<unknown>;

  searchWorkspace(input: {
    query: string;
    limit?: number;
    readableOnly?: boolean;
  }): Promise<unknown>;

  getActiveSelection(): Promise<{
    documentId: string | null;
    selectedText?: string;
    sectionId?: string;
  }>;

  proposePatch(input: {
    documentId: string;
    operationType: DocumentPatchOperationType;
    targetSectionId?: string;
    summary: string;
    rationale?: string;
    afterContent: string;
    sourceContextDocumentIds: string[];
  }): Promise<{ patchId: string }>;

  applyPatch(input: { patchId: string }): Promise<void>;
  rejectPatch(input: { patchId: string }): Promise<void>;

  createDocument(input: {
    type: WorkspaceDocumentType;
    title: string;
    contentMarkdown: string;
    sourceContextDocumentIds?: string[];
  }): Promise<{ documentId: string }>;
}
```

## Regla de tool design

- pocas tools
- poco solapamiento
- lecturas batch
- semántica clara
- resultados pequeños cuando sea posible

---

# Política de lectura del agente

## Regla 1 — index first

Siempre:

1. leer `WorkspaceIndex`
2. decidir qué docs importan
3. pedir detalle progresivo

## Regla 2 — summary before full

Orden por defecto:

1. summary
2. sections
3. range
4. full

## Regla 3 — no reread si la versión no cambió

Todo doc debe tener `version` o `contentHash`.

Si sigue igual:

- reusar resumen previo
- reusar resultado previo resumido
- no volver a golpear BD ni a inflar contexto

## Regla 4 — transcript no se lee completo salvo excepción

La transcripción debe exponerse en varias vistas:

- `transcript_summary`
- `recent_window`
- `speaker_chunks`
- `timeline` opcional
- `raw ranges`

## Regla 5 — las lecturas deben ser batch

Mal:

- una llamada por doc
- una llamada por fragmento
- una llamada por metadata

Bien:

```ts
readDocuments({
  items: [
    { documentId: noteId, mode: "summary" },
    {
      documentId: transcriptId,
      mode: "sections",
      sectionIds: ["recent_window"],
    },
    { documentId: contextId, mode: "summary" },
  ],
});
```

---

# Manejo de transcripción

## Problema

La transcripción es el documento más pesado. Históricamente causaba:

- demasiados tokens (costo excesivo)
- demasiadas lecturas
- latencia alta en cada respuesta del LLM

## Solución: Context Caching (Vertex AI / Gemini)

En lugar de depender exclusivamente de generar resúmenes con pérdida de detalle para ahorrar tokens, la estrategia principal durante el encuentro activo es usar **Context Caching**.

1. **Estabilización:** Mientras el audio llega, se guarda en DB el raw text.
2. **Congelamiento:** Cuando hay un punto estable (el médico pausa o termina), el backend toma esa transcripción base y la registra en el **Context Cache** del LLM (con un TTL corto, ej. 60 min).
3. **Reutilización:** Las peticiones subsecuentes del Agente solo envían el `cache_id` + el contexto dinámico actual (el prompt del médico + borradores). Esto derrumba latencia y costos manteniendo 100% de precisión clínica (0 alucinaciones por falta de contexto).

## Rol de los Resúmenes (Summaries)

Los resúmenes (`document_summaries`) ya no se usan para evitar leer la transcripción actual. Su nuevo rol es **longitudinal**:

- **Historial del paciente:** Para leer 10 encuentros pasados rápidamente (3,000 tokens en vez de 150,000).
- **UI:** Previsualizaciones para el médico en listas de encuentros.
- **Indexación:** Extracción de hechos estructurados (`StructuredFacts`) para búsqueda en BD.

---

# Sistema de patches y review

## Regla central

La IA **no puede escribir directo** al contenido final.

Todo write del agente debe pasar por:

1. propuesta
2. visualización / preview
3. aceptación o rechazo
4. aplicación
5. persistencia
6. auditoría

## Estados posibles

- `pending`
- `accepted`
- `rejected`
- `applied`
- `stale`

## Cuándo un patch se vuelve `stale`

Si se creó contra `documentVersionBase = 12` y el documento ya va en versión 13 o 14 sin rebase claro.

## UI mínima necesaria

- panel lateral o inline de cambios sugeridos
- resumen corto del cambio
- documento origen usado como contexto
- preview antes/después
- aceptar / rechazar

## Regla UX

El médico nunca debe sentir que la IA “le cambió la nota por debajo”.

---

# Qué hacer con Lexical

## Sí mantener Lexical

No necesitas cambiar de editor ahora.

## Pero cambiar su rol

Lexical debe renderizar estados como:

- `edit`
- `read_only`
- `streaming_preview`
- `patch_review`

## Input recomendado para el editor

```ts
type EditorAdapterInput = {
  snapshot: DocumentSnapshot | null;
  draft: DocumentDraftState | null;
  derived: DocumentDerivedState | null;
  pendingPatches?: DocumentPatch[];
  mode: "edit" | "read_only" | "streaming_preview" | "patch_review";
};
```

## Regla

Evita seguir construyendo lógica importante dentro de:

- TextArea
- plugins de Lexical
- remounts agresivos como solución general

---

# Backend / persistencia recomendada

## Tablas o entidades lógicas

### documents

Documento lógico principal.

### document_snapshots

Versiones canónicas guardadas.

### document_summaries

Resúmenes persistidos por versión.

### document_patches

Cambios sugeridos pendientes/aplicados.

### patch_audit

Auditoría de decisiones.

### transcript_chunks

Chunks raw de la transcripción.

### transcript_derived_views

Summary / recent window / vistas derivadas.

## Ejemplo conceptual

```ts
Documents -
  id -
  encounter_id -
  type -
  title -
  status -
  source -
  ai_readable -
  ai_writable -
  user_editable -
  current_version -
  created_at -
  updated_at;

DocumentSnapshots -
  id -
  document_id -
  version -
  content_markdown -
  lexical_json -
  sections_json -
  created_at;

DocumentSummaries -
  id -
  document_id -
  version -
  summary_short -
  summary_clinical -
  excerpt -
  created_at;

DocumentPatches -
  id -
  document_id -
  base_version -
  status -
  operation_type -
  target_section_id -
  summary -
  rationale -
  before_content -
  after_content -
  source_context_document_ids_json -
  created_by -
  created_at -
  accepted_at -
  rejected_at;

PatchAudit -
  id -
  patch_id -
  document_id -
  accepted_by_user_id -
  agent_task_type -
  source_document_ids_json -
  created_at -
  accepted_at -
  rejected_at;
```

---

# API / endpoints recomendados

## Lectura

```text
GET  /encounters/:id/workspace-index
POST /documents/read-batch
POST /workspace/search
GET  /documents/:id/snapshot
GET  /documents/:id/patches
```

## Escritura humana

```text
POST /documents/:id/save-draft
POST /documents/:id/commit-snapshot
```

## Escritura AI supervisada

```text
POST /patches/propose
POST /patches/:id/apply
POST /patches/:id/reject
POST /documents/create
```

## Derivados

```text
POST /transcripts/:id/recompute-summary
POST /documents/:id/recompute-summary
```

---

# Roadmap detallado

## Fase 0 — Contratos y diseño base

### Objetivo

Salir del estado mental “tab + markdown string” y pasar a “workspace + documentos + snapshots + drafts + patches”.

### Entregables

- tipos TypeScript base
- mapa de stores Zustand y compatibilidad temporal con providers actuales
- decisiones de permisos por documento
- endpoints contract draft
- `AGENTS.md` / `ARCHITECTURE.md` del repo actualizados

### Tareas

1. Definir `WorkspaceDocument`
2. Definir `DocumentSnapshot`
3. Definir `DocumentDraftState`
4. Definir `DocumentDerivedState`
5. Definir `DocumentPatch`
6. Definir `WorkspaceIndex`
7. Definir `ReadMode`
8. Escribir documento interno de arquitectura
9. Mapear explícitamente `DocumentContext`, `ContentContext`, `GenerationContext` y `TranscriptionContext` al modelo nuevo
10. Definir la topología inicial de stores en Zustand
11. Definir reglas de selector, suscripción, actions y side effects para cada store

### Criterio de éxito

Todos los próximos cambios usan este lenguaje común.

---

## Fase 1 — Refactor base del frontend

### Objetivo

Separar responsabilidades sin romper tabs, autosave, transcripción ni streaming actuales.

### Tareas

1. Crear una capa adaptadora entre el modelo actual y `WorkspaceDocument`
2. Crear `WorkspaceStore` en Zustand
3. Crear `DocumentSnapshotStore` en Zustand
4. Crear `DocumentDraftStore` en Zustand
5. Crear `DocumentDerivedStore` en Zustand
6. Crear `PatchStore` vacío o mínimo
7. Mover tabs y documento activo a leer desde `WorkspaceStore`
8. Mover el editor a consumir `snapshot + draft + derived`
9. Mantener Lexical, pero sacarle responsabilidad de fuente de verdad
10. Dejar los contexts actuales solo como compat layer mientras se migra la UI activa

### Qué no hacer aún

- no construir agent writer
- no meter multi-agent
- no meter embeddings si no son claramente necesarios
- no colapsar todo el dominio en un solo store global

### Criterio de éxito

Puedes abrir tabs, editar, autosavear y renderizar sin mezclar snapshot/draft/streaming.

---

## Fase 2 — Capa de lectura AI-ready

### Objetivo

Permitir que el agente lea bien sin reventar la base de datos ni el contexto.

### Tareas

1. Implementar `workspace-index`
2. Implementar `read-batch`
3. Añadir summaries persistidos por doc
4. Añadir `version` / `contentHash`
5. Crear `TranscriptDerivedViews`
6. Definir política de working set del agente
7. Añadir `searchWorkspace()` simple

### Criterio de éxito

El agente puede:

- ver qué docs existen
- pedir solo summaries
- pedir secciones/rangos cuando hace falta
- evitar rereads innecesarios

---

## Fase 3 — Agente read-only

### Objetivo

Construir primero un copiloto que sea útil leyendo, entendiendo y proponiendo, sin tocar contenido final.

### Capacidades

- resumir encuentro
- comparar transcripción vs nota
- detectar faltantes
- sugerir próximos pasos en chat
- crear documento nuevo opcional

### Tareas

1. Tool `listWorkspaceDocuments`
2. Tool `readDocuments`
3. Tool `searchWorkspace`
4. Tool `getActiveSelection`
5. Prompt del agente con política de lectura progresiva
6. UI lateral de chat con inspector de “docs leídos”

### Criterio de éxito

El agente ya es útil sin escribir directo nada.

---

## Fase 4 — Patches y review

### Objetivo

Introducir edición AI segura.

### Tareas

1. Implementar `proposePatch`
2. Implementar `PatchStore`
3. Panel de review accept/reject
4. Preview before/after
5. Manejo de `stale patches`
6. Auditoría básica

### Criterio de éxito

El agente puede sugerir cambios y el médico puede controlarlos granularmente.

---

## Fase 5 — Agente writer supervisado

### Objetivo

Permitir que el agente actúe sobre documentos editables, pero siempre por patch o creación de documento.

### Capacidades

- actualizar contexto
- proponer cambios a la nota
- generar documento resumen
- crear carta o documento adicional
- preparar draft de MIPRES

### Restricciones

- jamás escribir directo transcription raw
- jamás escribir directo uploaded raw document
- jamás mutar final note aprobada

### Criterio de éxito

El agent edita con seguridad y trazabilidad.

---

## Fase 6 — Producto clínico más fuerte

### Objetivo

Agregar capas especializadas solo cuando la base esté sólida.

### Posibles entregables

- templates opcionales por especialidad
- tags semánticos sugeridos en secciones
- MIPRES draft estructurado
- copy por sección a EHR
- patient history summary
- reglas de aprobación clínica

---

# Qué construir antes del AI agent completo

## Sí construir antes

- `WorkspaceDocument`
- stores separados
- summaries persistidos
- `workspace-index`
- `read-batch`
- transcript derived views
- patch model básico

## No posponer para después

Porque si lo pospones:

- el agente nacerá acoplado al modelo viejo
- vas a tener retrabajo
- vas a seguir leyendo demasiado contexto bruto

## Conclusión

No esperes a “terminar todo el frontend”.
Haz el refactor mínimo de base y luego construye un **agente read-only** encima.

---

# Strategy para single developer

## Regla 1

No hagas refactor masivo de todo a la vez.

## Regla 2

Cada fase debe dejar el producto usable.

## Regla 3

Haz flags o rutas de transición.

## Regla 4

Cuando metas una abstracción nueva, debe resolver un dolor real inmediato.

## Regla 5

Primero observabilidad, luego inteligencia.

---

# Vertical slices concretos

## Slice A — Nuevo modelo de documentos sin cambiar UX visible

- introducir `WorkspaceDocument`
- introducir snapshots/drafts
- mapear tabs actuales a documentos tipados
- mantener UI casi igual

## Slice B — Lectura AI progresiva

- endpoint `workspace-index`
- endpoint `read-batch`
- summaries por documento
- inspector de docs leídos en chat

## Slice C — Agente read-only útil

- “resume la consulta”
- “qué falta en la nota”
- “compara transcripción y plan”

## Slice D — Primer patch review

- patch replace section libre o bloque flexible
- panel accept/reject
- apply seguro

## Slice E — Creación de documentos derivados

- crear generated document
- crear context summary
- crear referral / memo / resumen

---

# Recomendación sobre secciones flexibles

## Nivel 1 — Sin parseo complejo

Solo markdown/string + títulos detectados.

## Nivel 2 — Secciones visibles/editables

UI reconoce bloques simples por heading.

## Nivel 3 — Tags semánticos opcionales

La IA puede sugerir que una sección parece `assessment` o `plan`.

## Nivel 4 — Templates opcionales

Una especialidad puede arrancar con plantilla, pero el core no depende de ella.

---

# Manejo de performance y reducción de llamadas a BD

## 1. Context Caching de Documentos Pesados (LLM Layer)

Para la transcripción o textos masivos que superan los 5k-10k tokens dentro del encuentro activo:

- No los pases repetidamente en el payload.
- Regístralos en Vertex AI / Gemini Context Cache con su versión actual.
- Envía el `cache_id` junto con los documentos dinámicos (borradores de notas) por cada turno.

## 2. Caché Interno de Sesión (LangGraph Layer)

Si no cambió la `version` de un documento clínico en BD y pertenece a documentos pequeños/medianos:

- El Checkpointer (Memoria del Agente) recuerda lo que leyó en turnos pasados.
- No se emite un query a PostgreSQL repitiendo la lectura de ese documento (salvo que el frontend notifique una versión nueva).

## 3. Resúmenes para Historias Clínicas Longitudinales

Si el agente necesita "Conocer la historia del último año":

- Jamás consultes ni cachees diez transcripciones crudas (HIPAA alert y derroche de recursos).
- Ejecuta `readDocuments` en `mode: summary` consultando `document_summaries` de encuentros anteriores.

## 3. Batch reads

Siempre agrupa lecturas.

## 4. Working set del agente

Mantén memoria corta y reutilizable.

```ts
export type AgentWorkingSet = {
  pinnedDocumentIds: string[];
  recentlyReadDocumentIds: string[];
  recentSummariesByDocumentId: Record<string, string>;
  currentTaskSummary?: string;
};
```

## 5. Invalidación simple

- cambia doc → invalida summary/snapshot de esa versión
- aplica patch → nueva versión y se invalidan derivados dependientes

---

# Testing mínimo recomendado por fase

## Fase 0-1

- tests de stores
- tests de selectors
- tests de versioning / dirty state

## Fase 2

- tests de `workspace-index`
- tests de `read-batch`
- tests de reuse por versión

## Fase 3

- tests de tool orchestration
- tests de transcript summary fallback

## Fase 4

- tests de patches stale
- tests de apply/reject
- tests de audit

## E2E mínimos

- abrir encounter y tabs
- editar nota y autosave
- agente lee docs y responde
- agente propone patch
- usuario acepta patch

---

# Riesgos y cómo controlarlos

## Riesgo 1 — hacer el modelo demasiado rígido

Mitigación: secciones flexibles y tags opcionales.

## Riesgo 2 — hacer demasiadas abstracciones muy pronto

Mitigación: implementar por slices y solo lo que soporte el siguiente paso.

## Riesgo 3 — que el agente lea demasiado

Mitigación: index first, summary before full, batch reads, version cache.

## Riesgo 4 — que la IA cambie documentos sin confianza

Mitigación: patches obligatorios + review + audit.

## Riesgo 5 — reventar el frontend con demasiados estados mezclados

Mitigación: snapshot/draft/derived separados.

---

# Decisiones concretas recomendadas

## Decisión 1

**Sí** separar ya `snapshot`, `draft` y `derived`.

## Decisión 2

**Sí** crear `WorkspaceDocument` tipado antes del agent writer.

## Decisión 3

**Sí** crear un agente read-only antes del writer.

## Decisión 4

**Sí** usar patches obligatorios para escritura AI.

## Decisión 5

**No** forzar `ClinicalSection` rígido por tipo de nota.

## Decisión 6

**Sí** usar secciones flexibles con posibles tags semánticos.

## Decisión 7

**No** dejar el AI agent para el final de todo el frontend.

## Decisión 8

**Sí** construir base + agente read-only relativamente pronto.

---

# Secuencia exacta que yo seguiría

## Semana / tramo 1

- definir tipos
- separar stores
- mapear tabs a `WorkspaceDocument`
- mantener UX actual funcionando

## Semana / tramo 2

- endpoint `workspace-index`
- summaries persistidos
- `read-batch`
- transcript derived views mínimas

## Semana / tramo 3

- primer agente read-only
- chat lateral útil
- inspector de documentos leídos

## Semana / tramo 4

- `DocumentPatch`
- patch preview
- accept/reject

## Semana / tramo 5

- agent writer supervisado
- creación de generated documents
- cambios sugeridos a note/context

## Semana / tramo 6+

- MIPRES draft estructurado
- patient history summary
- templates opcionales
- optimizaciones finas

---

# Planes de implementación para Codex

La idea no es pedir “haz todo el workspace AI-ready” en un solo chat. Conviene dividirlo en slices con write scope claro y criterio de cierre verificable.

## Plan Codex 1 — Tipos, stores base y arquitectura

### Objetivo

Crear el lenguaje común del sistema y la estructura inicial de stores en Zustand sin romper la UI actual.

### Alcance

- tipos `WorkspaceDocument`, `DocumentSnapshot`, `DocumentDraftState`, `DocumentDerivedState`, `DocumentPatch`, `WorkspaceIndex`
- carpeta base de stores
- documento corto de arquitectura actualizado
- reglas de selectors/actions

### Resultado esperado

- el repo ya tiene el vocabulario nuevo
- existe topología clara de stores
- todavía no cambia el comportamiento visible del editor

## Plan Codex 2 — WorkspaceStore + tabs + documento activo

### Objetivo

Mover la noción de tabs/documento activo al `WorkspaceStore` de Zustand.

### Alcance

- adaptar documentos actuales del backend a `WorkspaceDocument`
- mover selección de documento activo a `WorkspaceStore`
- conectar `TabBar` y `DocumentArea` al store nuevo
- dejar compatibilidad temporal con el sistema actual

### Resultado esperado

- tabs y documento activo ya no dependen del context viejo como owner principal
- no hay regresión al abrir, seleccionar o borrar documentos

## Plan Codex 3 — SnapshotStore + DraftStore + Lexical integration

### Objetivo

Separar por fin contenido canónico, draft local y estado del editor.

### Alcance

- `DocumentSnapshotStore`
- `DocumentDraftStore`
- adaptar `TextArea` y plugins para consumir `snapshot + draft`
- autosave del usuario contra draft + commit controlado

### Resultado esperado

- Lexical ya no actúa como fuente de verdad implícita
- editar una nota no mezcla snapshot persistido con draft local

## Plan Codex 4 — DerivedStore + streaming + transcripción

### Objetivo

Llevar streaming, progreso y contenido derivado a un store explícito.

### Alcance

- `DocumentDerivedStore`
- migrar generación por SSE al store
- migrar transcripción/read-only updates al store
- asegurar que patch preview y streaming tengan lugar natural

### Resultado esperado

- generación y transcripción ya no dependen de contexts legacy como owner principal
- el editor puede distinguir snapshot, draft y streaming sin hacks

## Plan Codex 5 — WorkspaceIndex + read-batch + AI read path

### Objetivo

Preparar el workspace para lecturas eficientes del agente.

### Alcance

- endpoint `workspace-index`
- endpoint `read-batch`
- summaries/version/content hash
- `AiSessionStore` mínimo para working set e inspector de lectura

### Resultado esperado

- el agente ya puede leer el workspace sin pedir todo
- existe base sólida para copiloto read-only

## Plan Codex 6 — PatchStore + review UI + safe write path

### Objetivo

Crear la ruta segura para escritura AI supervisada.

### Alcance

- `PatchStore`
- endpoints de propose/apply/reject
- UI de preview y accept/reject
- auditoría mínima

### Resultado esperado

- ningún cambio AI cae directo al contenido final
- el médico revisa y controla toda mutación generada por IA

## Plan Codex 7 — Limpieza de compat layer

### Objetivo

Retirar la capa vieja cuando las rutas activas ya usen el nuevo modelo.

### Alcance

- eliminar contexts legacy que ya no sean owners reales
- actualizar docs y `AGENTS.md`
- simplificar wiring del encounter detail

### Resultado esperado

- arquitectura final más simple
- menos ambigüedad para futuros chats y agentes

---

# Definition of done por milestone

## Milestone 1 — Workspace foundation

- tabs ya son documentos tipados
- snapshot/draft separados
- Lexical sigue funcionando
- no hay regresiones graves de edición

## Milestone 2 — AI readable workspace

- agente recibe índice pequeño
- puede pedir summaries y ranges
- no relee sin cambio de versión

## Milestone 3 — Read-only copilot

- responde usando docs correctos
- no depende de meter todo al contexto
- explica qué leyó

## Milestone 4 — Safe write path

- todo cambio AI llega como patch
- médico acepta o rechaza
- queda auditoría

## Milestone 5 — Advanced clinical workflow

- documentos derivados útiles
- MIPRES draft mejor soportado
- copy por partes o bloques

---

# Qué debe decir el AGENTS.md del repo

Tu `AGENTS.md` debería dejar muy claro esto:

1. Lexical es solo superficie de edición
2. no escribir IA directo al documento final
3. separar snapshot/draft/derived
4. usar `WorkspaceDocument` tipado
5. preferir lecturas progresivas
6. summaries por versión
7. patches obligatorios para edición AI
8. evitar secciones rígidas; usar secciones flexibles + tags opcionales

---

# Prompt guía para el coding agent

```text
We are evolving a React-based clinical multi-document workspace into an AI-ready architecture.

Key constraints:
- Keep Lexical as the visual editor
- Do not treat Lexical as source of truth
- Separate document snapshot, local draft, and derived/streaming state
- Represent tabs as typed WorkspaceDocuments
- The AI agent must read via a small workspace index and progressive document reads
- The AI agent must never overwrite final document content directly
- All AI writes must go through DocumentPatch proposal + review + apply/reject
- Do not force rigid ClinicalSection schemas by note type
- Use flexible sections with optional semantic tags instead
- Optimize for a solo founder shipping incrementally
- Avoid giant speculative refactors

Implementation priority:
1. define types and stores
2. refactor frontend state foundation
3. implement workspace index and batched reads
4. build read-only agent
5. implement patches and review UI
6. enable supervised AI writing
```

---

# Cierre

La arquitectura correcta para que esto tenga éxito no es:

**“terminar el frontend y luego agregar IA”**

o

**“agregar IA ya mismo sobre tabs y markdown bruto”**

La arquitectura correcta es:

**construir una base de workspace AI-ready, luego un agente read-only, luego un agente que sugiera patches, y solo después permitir escritura supervisada.**

Y sobre tu duda principal: sí, **yo retiraría la idea de `ClinicalSection` rígido** como pilar del sistema. La reemplazaría por:

**documentos tipados + secciones flexibles + etiquetas semánticas opcionales + patches por bloque**.

Eso te da mucha más probabilidad de éxito real en producto clínico.
