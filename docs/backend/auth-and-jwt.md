# Contratos de autenticación y JWT

## Sesión Django (`django_auth`)

- Usada por el navegador: cookie de sesión + CSRF en requests mutantes.
- Endpoints de negocio: encuentros, documentos (CRUD editor), pacientes, plantillas, etc.

## JWT de usuario (`POST /api/auth/jwt-token`)

- Audiencia: clientes que envían `Authorization: Bearer` al API (no es el mismo flujo que los callbacks de Cloud Functions en `documentos/api/callbacks.py`).
- Claims típicos: `user_id`, `exp`, `iat`, `iss`, `aud`, `jti`, `role`.
- Firma: `utils.jwt_settings.get_jwt_signing_key()` (misma clave que `JWT_SECRET_KEY` cuando está definida).
- Revocación: `jti` en caché / blacklist (`apps/users/api.py`).

## JWT de callbacks Cloud Functions (`utils.auth.JWTAuth`)

Verificado en:

- `PATCH /api/documento_by_function/{id}`
- `POST /api/document/generation-chunk`
- `POST /api/notify/transcription-complete`

Firma: misma clave vía `get_jwt_signing_key()`.

### Transcripción

Payload mínimo:

- `id_usuario` (int): médico dueño del documento
- `id_documento` (int): documento a actualizar
- `exp` (datetime)
- `purpose`: `"transcription"` (opcional pero recomendado)

Emitido por: `apps/generative_ai/api.py` usando `utils.service_jwt`.

### Generación de documento

Payload mínimo:

- `id_usuario`, `id_documento`, `id_proceso`, `exp`

### SSE

Payload mínimo:

- `id_documento`, `id_usuario`, `exp`, `purpose`: `"sse_connection"`

## JWT interno del broker del copiloto

- Usado por: `backend/apps/copilot/` cuando Django llama a `copilot-agent-service`.
- Se firma con: `COPILOT_SERVICE_SHARED_JWT` y no con `JWT_SECRET_KEY`.
- Claims mínimos:
  - `iss`: `app-api-service`
  - `sub`: `django-copilot-broker`
  - `aud`: `app-api-service`
  - `purpose`: `"copilot_internal_broker"`
  - `exp`
- Este contrato es temporal para `local` y `stg`. La deuda de migrarlo a OIDC/ID token queda registrada en [`../debt/copilot-agent-runtime.md`](../debt/copilot-agent-runtime.md).

## JWT interno de tools del copiloto

- Usado por: `copilot_agent/` cuando el runtime llama a los endpoints internos read-only de Django.
- Se firma con: `COPILOT_SERVICE_SHARED_JWT`.
- Claims mínimos:
  - `iss`: `copilot-agent-service`
  - `sub`: `copilot-agent-tools`
  - `aud`: `medical-api` (configurable vía `COPILOT_BACKEND_AUDIENCE`)
  - `purpose`: `"copilot_internal_tools"`
  - `run_id`, `thread_id`, `encounter_id`, `user_id`
  - `exp`
- Este contrato también forma parte de la deuda temporal de auth service-to-service registrada en [`../debt/copilot-agent-runtime.md`](../debt/copilot-agent-runtime.md).

## Variables de entorno relacionadas

| Variable | Uso |
|----------|-----|
| `JWT_SECRET_KEY` | Firma de todos los JWT anteriores cuando está definida y no es el placeholder `not-loaded` |
| `DJANGO_SECRET_KEY` | Fallback de firma si `JWT_SECRET_KEY` no aplica |
| `COPILOT_AGENT_BASE_URL` | Base URL del `copilot-agent-service` que consume Django |
| `COPILOT_SERVICE_SHARED_JWT` | Secreto compartido temporal del broker Django -> copilot agent |
| `COPILOT_AGENT_AUDIENCE` | Audiencia esperada por el agent runtime |
| `COPILOT_BACKEND_AUDIENCE` | Audiencia esperada por Django para las tools internas llamadas desde `copilot_agent` |
| `COPILOT_AGENT_TIMEOUT_SECONDS` | Timeout HTTP del cliente interno del copiloto |
| `TRANSCRIPTION_CLOUD_FUNCTION_URL` | URL HTTP de la función de transcripción |
| `GENERATE_DOCUMENT_CLOUD_FUNCTION_URL` | URL base de la función de generación (también se acepta `GENERATE_DOCUMENT_CLOUD_FUNCTION_BASE_URL` en develop) |
