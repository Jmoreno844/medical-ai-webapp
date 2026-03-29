# Logging y observabilidad

## Django

- Configuración central en [`config/settings/logging_utils.py`](../config/settings/logging_utils.py): función `build_console_logging(default_level)`.
- Nivel efectivo: variable de entorno **`DJANGO_LOG_LEVEL`** (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`). Valores inválidos caen al default del entorno.
- [`config/settings/base.py`](../config/settings/base.py) define `LOGGING` con default **INFO**.
- [`config/settings/develop.py`](../config/settings/develop.py) sobrescribe a **DEBUG** por defecto (sigue pudiendo ajustarse con `DJANGO_LOG_LEVEL`).
- [`config/settings/production.py`](../config/settings/production.py) usa **INFO** por defecto.
- **Tests**: [`config/settings/test.py`](../config/settings/test.py) hace `globals().pop("LOGGING", None)` tras importar `base` para seguir usando la configuración programática JSON existente (`configure_json_logging`), sin chocar con el dict `LOGGING` de base.

## Reglas de contenido

- No usar `print()` en código de aplicación; usar `logging.getLogger(__name__)`.
- Evitar en logs: texto clínico completo, payloads enteros hacia APIs, tokens, session keys, emails en claro salvo requisito de auditoría explícito y entorno controlado.

## Cloud Functions

- En [`cloud_functions/functions/services/django_api.py`](../../cloud_functions/functions/services/django_api.py), los chunks enviados a Django se resumen en log con **metadatos** (`document_id`, `process_id`, `chunk_len`, flags), no el texto del chunk.
- Los mensajes `logger.debug` en generación de documentos no deben incluir respuestas completas del modelo; solo éxito y forma del resultado.

## Frontend

Ver [`webapp/documentation/logging.md`](../../webapp/documentation/logging.md).
