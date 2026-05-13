# Contexts

Este directorio sigue agrupando gran parte del detalle de `Encuentro`, pero ya
no es el owner principal de todo el estado documental. El workspace state layer
vive en `src/workspace/`; los contexts orquestan side effects y sirven de
compatibilidad mientras termina la migración.

## Orden de providers

`AppProviders.tsx` compone:

1. `EncuentroProvider`
2. `DocumentProvider`
3. `ContentProvider`
4. `TranscriptionProvider`
5. `GenerationProvider`

Ese orden importa porque los providers se consumen entre sí.

## Qué es dueño de cada contexto

- `EncuentroContext`
  - datos generales del encuentro y paciente
- `DocumentContext`
  - compat wrapper temporal para documentos y operaciones de API
- `ContentContext`
  - compat bridge del editor sobre `DocumentSnapshotStore` + `DocumentDraftStore`
- `TranscriptionContext`
  - kickoff de transcripción, SSE y flags compartidos del encounter
- `GenerationContext`
  - plantillas, kickoff de generación y SSE
  - al completar generación, refresca el documento desde backend para rehidratar `contentJson` canónico además del markdown final

## Qué es dueño de cada store del workspace

- `WorkspaceStore`
  - tabs, orden de documentos, documento activo y visibilidad para AI
- `DocumentSnapshotStore`
  - contenido canónico conocido por documento y versión frontend
  - ahora guarda `contentJson` (canónico del editor) + `contentMarkdown` derivado/compat
- `DocumentDraftStore`
  - draft local editable, `isDirty`, `lastEditedAt` y `userEditedSinceLastCopilotTurn`
  - persiste tanto markdown como JSON del editor para recuperar drafts locales
- `DocumentDerivedStore`
  - streaming, modo del editor y estado transitorio de generación/transcripción
  - para transcripción también guarda bloques de vista con timestamp por sección, sin persistirlos en `contentMarkdown`
- `PatchStore`
  - preparación de preview/review de patches
- `AiSessionStore`
  - working set y metadata mínima para lectura del copiloto
  - también alimenta el debug client del copiloto mientras no exista la UX final

## Workspace migration

- `WorkspaceStore` es la nueva fuente de verdad de tabs y documento activo.
- `DocumentContext` delega esa parte al store nuevo para no romper consumidores
  legacy durante la migración.
- `ContentContext` ahora funciona como bridge sobre `DocumentSnapshotStore` y
  `DocumentDraftStore`.
- `DocumentDerivedStore` ya es el owner del streaming y del modo efectivo del
  editor.
- `snapshot` es la capa canónica frontend del contenido cargado.
- `snapshot.contentJson` es el canónico del editor rico; `snapshot.contentMarkdown` se mantiene como derivado/compat para saves legacy y pre-seed del copiloto.
- `draft` es la capa editable local del editor.
- `derived` es la capa transitoria para streaming y preview.
- `patch` sigue siendo preparación interna; todavía no hay write path AI final.
- `WorkspaceIndex` es el payload ligero para el runtime futuro del agente; no
  debe reconstruirse ad hoc en componentes de UI.
- el primer consumidor frontend del broker debe ser un panel/debug client que
  valide payload y stream antes de introducir el chat final.

## Semántica operativa de snapshot / draft

### Snapshot

- vive en `DocumentSnapshotStore`
- representa el último contenido canónico conocido por el frontend
- se actualiza al leer un documento, al guardar exitosamente, y al aplicar un patch del copiloto
- `savedAt` es local al frontend; sirve para orden y trazabilidad visual, no como contrato de persistencia clínica

### Draft

- vive en `DocumentDraftStore`
- `setDraftContent(...)` siempre marca `isDirty=true`
- `markDraftClean(...)` solo baja el flag; no reemplaza el contenido
- `resetDraftFromSnapshot(...)` vuelve a copiar el snapshot en el draft y deja `isDirty=false`
- el draft también se persiste localmente en navegador para sobrevivir refresh/cierre inesperado
- `userEditedSinceLastCopilotTurn` sobrevive al autosave y se limpia solo con `markCopilotTurnConsumed(...)` después de enviar contexto al copiloto

### Regla importante sobre `isDirty`

`isDirty` sigue usándose, pero ya no debe interpretarse como “el draft definitivamente difiere del snapshot”. En la práctica significa “hubo actividad local reciente del editor”.

Tiptap puede volver a disparar `update` al refrescar contenido desde snapshot y re-marcar el draft como dirty aunque el markdown derivado sea el mismo. Por eso los caminos sensibles al copiloto deben comparar contenido normalizado, no basarse solo en el booleano.

### Save path del editor

1. `TextArea` monta Tiptap 3 como editor principal.
2. cada `update` publica `draft.contentJson` inmediato y deriva `draft.contentMarkdown`.
3. el draft local se persiste en navegador con debounce corto (~400 ms).
4. el editor dispara autosave backend con debounce corto (~1 s).
5. `saveContent(...)` compara contra snapshot por markdown normalizado y JSON canónico.
6. Si el contenido es igual, evita el save HTTP y solo limpia el draft.
7. Si el contenido cambió, persiste `content_json` + `content_markdown`, actualiza snapshot y limpia el draft.

### Flush de salida / navegación

- el editor intenta `flushDirtyDrafts(...)` al cambiar de documento, al ocultarse la pestaña (`visibilitychange`) y en `pagehide`
- en salida también dispara un `fetch(..., { keepalive: true })` best-effort hacia el mismo write path del editor, pero solo si el draft local sigue siendo distinto del snapshot
- ese flush solo aplica a editores montados; si no existe editor montado, el draft local persistido sigue siendo la red de seguridad
- no existe todavía un write path especial vía `sendBeacon`; el primer mecanismo de protección sigue siendo `draft local persistido + save HTTP normal`

### Force-save antes del copiloto

`useCopilotPanelController.sendMessage()` llama `flushDirtyDrafts(...)` antes de construir `WorkspaceIndex`.

- solo los editores montados participan porque el registro vive en `forceSaveRegistry.ts`
- si un editor no está montado, el documento puede seguir dirty y salir sin `contentMarkdown` en el payload al agente
- `buildWorkspaceIndex()` compensa parte de esto comparando `draft` vs `snapshot` para no excluir falsos dirty causados por re-render del editor

## Restricciones importantes

- Mantén la lógica de `EventSource` dentro de `TranscriptionContext` y `GenerationContext`.
- No devuelvas tabs/documento activo a `DocumentContext`; esa migración ya está
  hecha hacia `WorkspaceStore`.
- No muevas streaming visible al `ContentContext`; el editor debe resolver la
  precedencia `derived > draft > snapshot`.
- `ContentContext` es compatibilidad del editor, no owner final del estado del
  workspace.
- Evita duplicar el mismo estado en componentes hijos si ya existe en un contexto o store.
- `features/` debe componer UI sobre estos providers/stores, no volver a crear managers paralelos del mismo flujo.
- Si una lógica reusable nace desde un feature, extráela como helper sin ownership global o muévela al context dueño.
