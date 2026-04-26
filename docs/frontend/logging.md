# Logging en frontend

## Objetivo

- En desarrollo y staging, ver trazas útiles sin dispersar `console.*` por todo el código.
- En producción, no depender de la consola del navegador para diagnóstico ni filtrar datos sensibles.

## Módulo central

Usar siempre `webapp/src/lib/logger.ts`:

- `logger.debug`
- `logger.info`
- `logger.warn`
- `logger.error`
- Opcional: `createChildLogger("NombreModulo")`

## Comportamiento

- En `dev` y `staging`, el logger puede emitir trazas.
- En producción, Vite elimina llamadas a `console` con `esbuild.drop`.
- ESLint mantiene `no-console` para evitar regresiones fuera de `logger.ts`.

## Variable de entorno

| Variable | Efecto |
|----------|--------|
| `VITE_LOG_LEVEL=silent` | Desactiva todo el logging incluso en `dev` / `staging`. |

## Qué no loguear

- Contraseñas, tokens JWT completos, cookies y cabeceras `Authorization`.
- Contenido clínico completo o payloads con datos de pacientes.
- URLs firmadas completas de subida a GCS.

## Relación con otros servicios

- Política del backend: [`../backend/logging.md`](../backend/logging.md).
- Flujo global del sistema: [`../architecture/system-overview.md`](../architecture/system-overview.md).
