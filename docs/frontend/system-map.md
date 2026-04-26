# Mapa del frontend

Documento de referencia rápida del `webapp` (React 18 + Vite + TypeScript). Los contratos HTTP con el backend están en inglés; la UI puede estar en español.

## Entrada y routing

- `src/main.tsx` — montaje de React y `RouterProvider`.
- `src/router.tsx` — rutas: `/home`, `/encuentro`, `/encuentro/:id`, `/plantillas`, `/login`, `/registro`, etc.
- `src/App.tsx` — shell con `Outlet` para rutas hijas.

## Layout y navegación

- `src/features/app_layout/SpecialLayout.tsx` — layout autenticado con sidebar.
- `src/features/app_layout/components/Sidebar.tsx` — navegación principal.
- `src/features/app_layout/hooks/useNavigationItems.ts` — ítems del menú.

## Estado global (providers + stores)

| Contexto         | Ruta                                    | Rol                                                                |
| ---------------- | --------------------------------------- | ------------------------------------------------------------------ |
| Auth             | `src/commons/contexts/AuthContext.tsx`  | Sesión, usuario, login/logout.                                     |
| Documentos       | `src/contexts/DocumentContext.tsx`      | Compat wrapper temporal para CRUD y bridge hacia `WorkspaceStore`. |
| Contenido editor | `src/contexts/ContentContext.tsx`       | Compat bridge del editor sobre snapshot + draft.                   |
| Encuentro        | `src/contexts/EncuentroContext.tsx`     | Datos del encuentro, paciente y fechas.                            |
| Transcripción    | `src/contexts/TranscriptionContext.tsx` | Audio, kickoff, SSE y flags del encounter.                         |
| Generación       | `src/contexts/GenerationContext.tsx`    | Plantillas, kickoff y SSE de generación.                           |

| Store      | Ruta                                            | Rol                                                                          |
| ---------- | ----------------------------------------------- | ---------------------------------------------------------------------------- |
| Workspace  | `src/workspace/stores/workspaceStore.ts`        | Tabs, documento activo, orden y visibilidad AI.                              |
| Snapshot   | `src/workspace/stores/documentSnapshotStore.ts` | Contenido canónico conocido y versión frontend por documento.                |
| Draft      | `src/workspace/stores/documentDraftStore.ts`    | Draft local editable e `isDirty`.                                            |
| Derived    | `src/workspace/stores/documentDerivedStore.ts`  | Streaming, modo del editor y estado transitorio de generación/transcripción. |
| Patch      | `src/workspace/stores/patchStore.ts`            | Preview/review de patches en preparación.                                    |
| AI session | `src/workspace/stores/aiSessionStore.ts`        | Working set y metadata de lectura futura del copiloto.                       |

`src/contexts/AppProviders.tsx` compone los providers en la página de detalle de encuentro.
Para esa pantalla, `contexts/` es el owner de SSE y kickoff de procesos; el
workspace state vive en `src/workspace/`; `features/` se limita a consumir y
renderizar.

## Ciclo de vida del contenido del editor

### Capas de contenido

El contenido documental en frontend no vive solo en Lexical. Se reparte en tres capas explícitas:

| Capa       | Store / owner                                   | Rol                                                                         |
| ---------- | ----------------------------------------------- | --------------------------------------------------------------------------- |
| `snapshot` | `src/workspace/stores/documentSnapshotStore.ts` | Último contenido canónico conocido por el frontend para ese documento.      |
| `draft`    | `src/workspace/stores/documentDraftStore.ts`    | Contenido editable local, mutable por el médico y por callbacks del editor. |
| `derived`  | `src/workspace/stores/documentDerivedStore.ts`  | Contenido transitorio no canónico: streaming, preview, patch review.        |

`ContentContext` es solo el bridge de compatibilidad del editor sobre `snapshot + draft`; no es el owner definitivo del estado.

### Regla de precedencia

La precedencia del contenido visible en `Lexical` es:

1. `derived` si el documento activo está en streaming o preview
2. `draft` si existe
3. `snapshot`

Eso evita que `Lexical` se convierta en la fuente de verdad implícita.

### Qué significan las variables clave

| Variable                         | Dónde vive                               | Semántica actual                                                                                                                                                                                         |
| -------------------------------- | ---------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `localUnsavedContent`            | `DocumentDraftState`                     | Último markdown local que el editor emitió para ese documento.                                                                                                                                           |
| `isDirty`                        | `DocumentDraftState`                     | Hay draft local pendiente o recién re-emitido por Lexical. No significa necesariamente que el contenido difiera materialmente del snapshot.                                                              |
| `userEditedSinceLastCopilotTurn` | `DocumentDraftState`                     | El médico tocó el documento desde el último turno del copiloto. Sobrevive al autosave; se limpia solo después de enviar un mensaje al copiloto.                                                          |
| `contentMarkdown`                | `DocumentSnapshot` / `WorkspaceDocument` | Markdown canónico conocido en frontend. `WorkspaceDocument.contentMarkdown` es el valor cargado con el documento; `DocumentSnapshot.contentMarkdown` pasa a ser la capa canónica una vez leído/guardado. |
| `version`                        | `DocumentSnapshot` / `WorkspaceDocument` | Baseline de frontend usado por `WorkspaceIndex`. No debe asumirse como versión autoritativa de persistencia del backend salvo que el contrato lo haga explícito.                                         |
| `savedAt`                        | `DocumentSnapshot`                       | Timestamp local del último refresh/save que actualizó el snapshot.                                                                                                                                       |

### Autosave y comparación de contenido

El editor usa `AutoSavePlugin` para serializar Lexical a markdown y publicar cambios al draft local.

- Cada update de Lexical ejecuta `onDraftChange` y llama `setDraftContent(documentId, content)`.
- `setDraftContent(...)` siempre deja `isDirty=true` y `userEditedSinceLastCopilotTurn=true`.
- El autosave difiere el save real por `saveInterval` (actualmente 2000 ms), salvo que se fuerce manualmente.

`ContentContext.saveContent(...)` decide si hace red o no usando comparación normalizada de strings, no hashes:

- normaliza `\r\n`, `\r`, múltiples saltos de línea, espacios/tabs repetidos y `trim()`
- si `normalize(snapshot.contentMarkdown) === normalize(content)`:
  - no hace `PATCH /api/documents/...`
  - resetea el draft desde el snapshot
  - marca `isDirty=false`
- si el contenido sí cambió:
  - hace save HTTP
  - actualiza `snapshot`
  - resetea el draft desde el snapshot nuevo
  - marca `isDirty=false`

No existe hoy un hash frontend para decidir el skip del autosave; la decisión es content-based.

### Por qué `isDirty` puede seguir en `true` después de un save correcto

Lexical puede volver a disparar `onChange` después de que `DocumentContentPlugin` aplica contenido refrescado desde snapshot o después de aplicar un patch del copiloto. Eso puede re-hidratar el draft con el mismo contenido semántico y dejar `isDirty=true` temporalmente.

Por eso `buildWorkspaceIndex()` ya no excluye el pre-seed solo por `isDirty`. Antes de omitir `contentMarkdown`, compara el draft contra el snapshot con la misma normalización que usa `saveContent()`:

- `draft != snapshot` → excluir `contentMarkdown` del payload AI
- `draft == snapshot` → incluir `contentMarkdown` aunque `isDirty` siga en `true`

## Envío al copiloto

Antes de construir `WorkspaceIndex`, `useCopilotPanelController.sendMessage()` intenta vaciar drafts sucios con `flushDirtyDrafts(...)`.

- `forceSaveRegistry.ts` solo puede forzar save de editores montados que hayan registrado su callback.
- si un documento sucio no tiene editor montado, el flush lo omite y el payload AI puede salir sin `contentMarkdown` para ese doc.
- después del flush, `buildWorkspaceIndex()` decide por documento si pre-seedear o no el contenido completo.

### Reglas de pre-seed en `WorkspaceIndex`

`document.contentMarkdown` se envía al agente solo si:

- el documento es `aiWritable`
- no está oculto para AI
- no está en streaming (`derived.inProgress + streamingContent`)
- y el draft local no difiere materialmente del snapshot/canonical actual

Si `preSeedExcluded=true` en los logs del chat debug, el agente no recibió el markdown completo y tendrá que usar `read_document(...)` antes de proponer un patch.

## API cliente

- `src/commons/utils/axiosInstance.ts` — `baseURL` desde `VITE_API_URL`, credenciales, CSRF e interceptores.
- `src/api/` — clientes tipados hacia recursos REST.

## Features principales

| Área                                 | Carpeta                                         |
| ------------------------------------ | ----------------------------------------------- |
| Inicio                               | `src/features/home/`                            |
| Login / registro                     | `src/features/login/`, `src/features/registro/` |
| Cabecera encuentro (audio, paciente) | `src/features/encuentroHeader/`                 |
| Editor y pestañas de documentos      | `src/features/encuentroTextArea/`               |
| Plantillas                           | `src/features/plantillas/`                      |
| Páginas estáticas                    | `src/pages/`                                    |

### Cabecera de audio y transcripción

`VoiceRecorder` consume `TranscriptionContext` directamente. En transcripción
por secciones, grabar ya crea una sesión y abre SSE; la cabecera ya no muestra
un botón separado de `Transcribir`. La cabecera expone un botón principal de
sesión `Grabar / Detener transcripción / Reanudar` y un control secundario de
`Pausar / Reanudar` solo mientras la sesión sigue abierta. `Detener
transcripción` cierra la sesión activa para que el backend consolide la
transcripción near realtime; `Reanudar` abre una nueva sesión sobre el mismo
encuentro.

## Observabilidad

- Usar `src/lib/logger.ts` en lugar de `console.*`.
- Detalle: [`logging.md`](logging.md).
