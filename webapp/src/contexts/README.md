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

## Qué es dueño de cada store del workspace

- `WorkspaceStore`
  - tabs, orden de documentos, documento activo y visibilidad para AI
- `DocumentSnapshotStore`
  - contenido canónico conocido por documento y versión frontend
- `DocumentDraftStore`
  - draft local editable, `isDirty` y `lastEditedAt`
- `DocumentDerivedStore`
  - streaming, modo del editor y estado transitorio de generación/transcripción
- `PatchStore`
  - preparación de preview/review de patches
- `AiSessionStore`
  - working set y metadata mínima para lectura futura del copiloto

## Workspace migration

- `WorkspaceStore` es la nueva fuente de verdad de tabs y documento activo.
- `DocumentContext` delega esa parte al store nuevo para no romper consumidores
  legacy durante la migración.
- `ContentContext` ahora funciona como bridge sobre `DocumentSnapshotStore` y
  `DocumentDraftStore`.
- `DocumentDerivedStore` ya es el owner del streaming y del modo efectivo del
  editor.
- `snapshot` es la capa canónica frontend del contenido cargado.
- `draft` es la capa editable local del editor.
- `derived` es la capa transitoria para streaming y preview.
- `patch` sigue siendo preparación interna; todavía no hay write path AI final.
- `WorkspaceIndex` es el payload ligero para el runtime futuro del agente; no
  debe reconstruirse ad hoc en componentes de UI.

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
