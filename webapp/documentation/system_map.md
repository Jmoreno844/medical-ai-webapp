# Mapa del frontend — estado actual

Documento de referencia rápida del `webapp` (React 18 + Vite + TypeScript). Los contratos HTTP con el backend están en inglés; la UI puede estar en español.

## Entrada y routing

- [`src/main.tsx`](../src/main.tsx) — montaje de React y `RouterProvider`.
- [`src/router.tsx`](../src/router.tsx) — rutas: `/home`, `/encuentro`, `/encuentro/:id`, `/plantillas`, `/login`, `/registro`, etc.
- [`src/App.tsx`](../src/App.tsx) — shell con `Outlet` para rutas hijas.

## Layout y navegación

- [`src/features/app_layout/SpecialLayout.tsx`](../src/features/app_layout/SpecialLayout.tsx) — layout autenticado con sidebar.
- [`src/features/app_layout/components/Sidebar.tsx`](../src/features/app_layout/components/Sidebar.tsx) — navegación principal.
- [`src/features/app_layout/hooks/useNavigationItems.ts`](../src/features/app_layout/hooks/useNavigationItems.ts) — ítems del menú.

## Estado global (contextos)

| Contexto | Ruta | Rol |
|----------|------|-----|
| Auth | [`src/commons/contexts/AuthContext.tsx`](../src/commons/contexts/AuthContext.tsx) | Sesión, usuario, login/logout. |
| Documentos | [`src/contexts/DocumentContext.tsx`](../src/contexts/DocumentContext.tsx) | Lista de documentos del encuentro, CRUD ligado a API. |
| Contenido editor | [`src/contexts/ContentContext.tsx`](../src/contexts/ContentContext.tsx) | Contenido del documento activo, caché, guardado. |
| Encuentro | [`src/contexts/EncuentroContext.tsx`](../src/contexts/EncuentroContext.tsx) | Datos del encuentro, paciente, fechas. |
| Transcripción | [`src/contexts/TranscriptionContext.tsx`](../src/contexts/TranscriptionContext.tsx) | Audio, SSE de transcripción, flags. |
| Generación | [`src/contexts/GenerationContext.tsx`](../src/contexts/GenerationContext.tsx) | Plantillas, SSE de generación, modal. |

[`src/contexts/AppProviders.tsx`](../src/contexts/AppProviders.tsx) compone los providers en la página de detalle de encuentro.

## API cliente

- [`src/commons/utils/axiosInstance.ts`](../src/commons/utils/axiosInstance.ts) — `baseURL` desde `VITE_API_URL`, credenciales, CSRF, interceptores.
- [`src/api/`](../src/api/) — clientes tipados hacia recursos REST (p. ej. encuentros).

## Features principales

| Área | Carpeta |
|------|---------|
| Inicio | `src/features/home/` |
| Login / registro | `src/features/login/`, `src/features/registro/` |
| Cabecera encuentro (audio, paciente) | `src/features/encuentroHeader/` |
| Editor y pestañas de documentos | `src/features/encuentroTextArea/` |
| Plantillas | `src/features/plantillas/` |
| Páginas estáticas | `src/pages/` |

## Logging (observabilidad en cliente)

- Usar [`src/lib/logger.ts`](../src/lib/logger.ts) en lugar de `console.*`.
- Detalle: [logging.md](logging.md).

## Estáticos y estilo

- Tailwind + componentes UI en `src/commons/components/ui/`.
- Assets públicos referenciados como `/archivo.svg` desde `public/` (Vite).
