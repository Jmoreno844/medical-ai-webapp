# Webapp

SPA React + TypeScript + Vite usada por el médico para grabar, transcribir, editar y generar documentos clínicos.

## Leer primero

- [`../docs/frontend/README.md`](../docs/frontend/README.md)
- [`src/contexts/README.md`](src/contexts/README.md)

## Comandos comunes

```bash
npm install
npm run dev
npm run lint
npm run build
```

## Mapa rápido

- `src/router.tsx` — rutas
- `src/commons/` — utilidades compartidas, `axiosInstance`, auth context
- `src/contexts/` — estado principal del detalle de encuentro
- `src/features/encuentroHeader/` — audio, paciente, transcripción
- `src/features/encuentroTextArea/` — editor, tabs, generación documental

## Notas de mantenimiento

- La fuente de verdad actual para el detalle de encuentro pasa por `AppProviders` y los contexts.
- Si cambias SSE o generación, revisa tanto `GenerationContext` como `TranscriptionContext`.
- Los hooks viejos bajo `src/features/.../hooks/` no siempre representan la ruta activa del producto.
