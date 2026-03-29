# Logging en el frontend

## Objetivo

- En **desarrollo** y **tests**, ver trazas útiles en la consola del navegador sin dispersar `console.*` por todo el código.
- En **producción**, no depender de logs en cliente para diagnóstico (y no filtrar datos sensibles por la consola del usuario).

## Módulo central

Usar siempre [`src/lib/logger.ts`](../src/lib/logger.ts):

- `logger.debug` / `logger.info` / `logger.warn` / `logger.error`
- Opcional: `createChildLogger("NombreModulo")` para prefijar mensajes.

Comportamiento:

- Los métodos **no emiten nada** si no estás en entorno de desarrollo o modo `test`, salvo que actives el flag de silencio (ver abajo).
- En **producción**, el bundle suele eliminar llamadas a `console` vía `esbuild.drop` en `vite.config.ts`; el `logger` delega en `console`, así que esa capa sigue siendo coherente.

## Variables de entorno

| Variable | Efecto |
|----------|--------|
| `VITE_LOG_LEVEL=silent` | Desactiva todo el logging del `logger` incluso en `dev` / `test`. |

`import.meta.env.DEV` y `import.meta.env.MODE === "test"` controlan si el logger está habilitado.

## Build de producción

En [`vite.config.ts`](../vite.config.ts), con `NODE_ENV === "production"` se usa:

```ts
esbuild: { drop: ["console", "debugger"] }
```

Eso elimina llamadas a `console` del bundle. El código debe seguir usando `logger` (no `console` directo) para que ESLint (`no-console`) evite regresiones.

## Qué no loguear

- Contraseñas, tokens JWT completos, cookies, cabeceras `Authorization`.
- Contenido clínico completo o payloads de API con datos de pacientes.
- URLs firmadas completas (p. ej. subida a GCS); basta `has_url=true` o metadatos.

## Backend y Cloud Functions

La política de niveles en Django y el saneamiento de logs en Cloud Functions están descritos en [`backend/documentation/logging_and_observability.md`](../../backend/documentation/logging_and_observability.md).
