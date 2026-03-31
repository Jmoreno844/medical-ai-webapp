# Frontend

El `webapp/` es la SPA usada por el médico. Se encarga de autenticación en navegador, grabación/subida de audio, edición de documentos y consumo de SSE.

## Qué leer aquí

- [`system-map.md`](system-map.md) — mapa rápido de rutas, contextos, features y cliente API.
- [`logging.md`](logging.md) — uso de `src/lib/logger.ts`, comportamiento por entorno y reglas de no loguear datos sensibles.
- Trazas locales: `src/tracing.ts` (OTLP vía `VITE_OTEL_EXPORTER_OTLP_TRACES_URL`, proxy en `vite.config.ts`); producción: ver [`../backend/tracing.md`](../backend/tracing.md).

## Mapa rápido del código

- `webapp/src/router.tsx` — rutas principales.
- `webapp/src/contexts/` — estado global del detalle de encuentro.
- `webapp/src/features/encuentroHeader/` — audio, paciente y acciones de cabecera.
- `webapp/src/features/encuentroTextArea/` — editor, pestañas y generación de documentos.
- `webapp/src/commons/utils/axiosInstance.ts` — cliente HTTP con CSRF y cookies (propagación W3C vía instrumentación XHR cuando OTel está activo).
