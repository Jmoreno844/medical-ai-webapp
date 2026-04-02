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

| Contexto | Ruta | Rol |
|----------|------|-----|
| Auth | `src/commons/contexts/AuthContext.tsx` | Sesión, usuario, login/logout. |
| Documentos | `src/contexts/DocumentContext.tsx` | Compat wrapper temporal para CRUD y bridge hacia `WorkspaceStore`. |
| Contenido editor | `src/contexts/ContentContext.tsx` | Compat bridge del editor sobre snapshot + draft. |
| Encuentro | `src/contexts/EncuentroContext.tsx` | Datos del encuentro, paciente y fechas. |
| Transcripción | `src/contexts/TranscriptionContext.tsx` | Audio, kickoff, SSE y flags del encounter. |
| Generación | `src/contexts/GenerationContext.tsx` | Plantillas, kickoff y SSE de generación. |

| Store | Ruta | Rol |
|-------|------|-----|
| Workspace | `src/workspace/stores/workspaceStore.ts` | Tabs, documento activo, orden y visibilidad AI. |
| Snapshot | `src/workspace/stores/documentSnapshotStore.ts` | Contenido canónico conocido y versión frontend por documento. |
| Draft | `src/workspace/stores/documentDraftStore.ts` | Draft local editable e `isDirty`. |
| Derived | `src/workspace/stores/documentDerivedStore.ts` | Streaming, modo del editor y estado transitorio de generación/transcripción. |
| Patch | `src/workspace/stores/patchStore.ts` | Preview/review de patches en preparación. |
| AI session | `src/workspace/stores/aiSessionStore.ts` | Working set y metadata de lectura futura del copiloto. |

`src/contexts/AppProviders.tsx` compone los providers en la página de detalle de encuentro.
Para esa pantalla, `contexts/` es el owner de SSE y kickoff de procesos; el
workspace state vive en `src/workspace/`; `features/` se limita a consumir y
renderizar.

### Regla del editor

La precedencia del contenido visible en `Lexical` es:

1. `derived` si el documento activo está en streaming o preview
2. `draft` si existe
3. `snapshot`

Eso evita que `Lexical` se convierta en la fuente de verdad implícita.

## API cliente

- `src/commons/utils/axiosInstance.ts` — `baseURL` desde `VITE_API_URL`, credenciales, CSRF e interceptores.
- `src/api/` — clientes tipados hacia recursos REST.

## Features principales

| Área | Carpeta |
|------|---------|
| Inicio | `src/features/home/` |
| Login / registro | `src/features/login/`, `src/features/registro/` |
| Cabecera encuentro (audio, paciente) | `src/features/encuentroHeader/` |
| Editor y pestañas de documentos | `src/features/encuentroTextArea/` |
| Plantillas | `src/features/plantillas/` |
| Páginas estáticas | `src/pages/` |

## Observabilidad

- Usar `src/lib/logger.ts` en lugar de `console.*`.
- Detalle: [`logging.md`](logging.md).
