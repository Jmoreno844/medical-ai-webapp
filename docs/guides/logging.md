# Logging y Observabilidad

Este documento describe las políticas y configuraciones de logging para todo el stack del Proyecto AI Médico (Frontend, Backend y Cloud Functions).

## 1. Reglas Generales de Contenido (Aplica a todo el stack)

- **Nunca** usar `print()` o `console.log()` directamente en el código de aplicación. Usar siempre los loggers configurados.
- **Datos Sensibles**: Evitar en logs:
  - Texto clínico completo o transcripciones.
  - Payloads enteros hacia APIs con datos de pacientes.
  - Contraseñas, tokens JWT completos, cookies, session keys o cabeceras `Authorization`.
  - Emails en claro (salvo requisito de auditoría explícito y entorno controlado).
  - URLs firmadas completas (p. ej. subida a GCS); es suficiente loguear metadatos como `has_url=true`.

---

## 2. Frontend (React / Vite)

### Módulo Central
Usar siempre `src/lib/logger.ts`:
- `logger.debug` / `logger.info` / `logger.warn` / `logger.error`
- Opcional: `createChildLogger("NombreModulo")` para prefijar mensajes.

### Comportamiento por Entorno
- **Desarrollo y Test**: Los métodos emiten a la consola del navegador.
- **Producción**: Los métodos **no emiten nada**. Además, el bundle de Vite elimina las llamadas a `console` vía `esbuild.drop: ["console", "debugger"]` en `vite.config.ts`.
- **ESLint**: La regla `no-console` está activa para evitar el uso directo de `console.*` fuera del archivo `logger.ts`.

### Variables de Entorno
| Variable | Efecto |
|----------|--------|
| `VITE_LOG_LEVEL=silent` | Desactiva todo el logging del `logger` incluso en `dev` / `test`. |

---

## 3. Backend (Django)

### Configuración
- Configuración central en `backend/config/settings/logging_utils.py` mediante la función `build_console_logging(default_level)`.
- Nivel efectivo: Controlado por la variable de entorno **`DJANGO_LOG_LEVEL`** (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`). Valores inválidos caen al default del entorno.

### Comportamiento por Entorno
- **Base** (`base.py`): Define `LOGGING` con default **INFO**.
- **Desarrollo** (`develop.py`): Sobrescribe a **DEBUG** por defecto (sigue pudiendo ajustarse con `DJANGO_LOG_LEVEL`).
- **Producción** (`production.py`): Usa **INFO** por defecto.
- **Tests** (`test.py`): Elimina el dict `LOGGING` de base (`globals().pop("LOGGING", None)`) para usar la configuración programática JSON existente (`configure_json_logging`).

---

## 4. Cloud Functions

- **Saneamiento de Chunks**: En `cloud_functions/functions/services/django_api.py`, los chunks enviados a Django se resumen en el log con **metadatos** (`document_id`, `process_id`, `chunk_len`, flags), no con el texto del chunk.
- **Respuestas de IA**: Los mensajes `logger.debug` en la generación de documentos no deben incluir respuestas completas del modelo; solo el éxito de la operación y la forma/tamaño del resultado.
