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

## Estado global (contextos)

| Contexto | Ruta | Rol |
|----------|------|-----|
| Auth | `src/commons/contexts/AuthContext.tsx` | Sesión, usuario, login/logout. |
| Documentos | `src/contexts/DocumentContext.tsx` | Lista de documentos del encuentro y CRUD ligado a API. |
| Contenido editor | `src/contexts/ContentContext.tsx` | Contenido del documento activo, caché y guardado. |
| Encuentro | `src/contexts/EncuentroContext.tsx` | Datos del encuentro, paciente y fechas. |
| Transcripción | `src/contexts/TranscriptionContext.tsx` | Audio, SSE de transcripción y flags. |
| Generación | `src/contexts/GenerationContext.tsx` | Plantillas, SSE de generación y modal. |

`src/contexts/AppProviders.tsx` compone los providers en la página de detalle de encuentro.
Para esa pantalla, `contexts/` es el owner de SSE, kickoff de procesos y estado compartido; `features/` se limita a consumir y renderizar.

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
