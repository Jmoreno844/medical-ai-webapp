# Logging en backend

## Configuración

- Configuración central en `backend/config/settings/logging_utils.py` mediante `build_console_logging(default_level)`.
- Nivel efectivo controlado por `DJANGO_LOG_LEVEL` (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`).
- El filtro `TraceContextFilter` añade `trace_id` y `span_id` del span OTel activo a cada registro (formato de consola: `trace_id=… span_id=…`). En GCP, si existe `GOOGLE_CLOUD_PROJECT` / `GCP_PROJECT`, también se calcula `google_cloud_trace` para correlación con Cloud Logging / Cloud Trace (ver [tracing.md](tracing.md)).

## Comportamiento por entorno

- `config.settings.base` define `LOGGING` con default `INFO`.
- `config.settings.develop` sube el default a `DEBUG`.
- `config.settings.stg` usa JSON logging para Cloud Logging y conserva correlación con Cloud Trace.
- `config.settings.production` mantiene `INFO`.
- `config.settings.test` elimina el dict `LOGGING` para seguir usando la configuración JSON de tests.

## Reglas de contenido

- Nunca usar `print()` en código de aplicación.
- Usar `logging.getLogger(__name__)`.
- No loguear texto clínico completo, payloads enteros, tokens, session keys ni credenciales.
- Si hace falta trazar una operación sensible, loguear metadatos y no contenido.

## Relación con otros servicios

- El frontend usa su propia política en [`../frontend/logging.md`](../frontend/logging.md).
- Cloud Functions debe seguir el mismo principio de saneamiento: metadatos sí, contenido clínico no.
