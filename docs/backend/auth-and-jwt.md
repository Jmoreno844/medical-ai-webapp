# Contratos de autenticación y JWT

## FastAPI browser JWTs (`/api/v1/auth/*`)

- FastAPI uses HttpOnly browser cookies for `browser_access` and
  `browser_refresh` tokens, plus `_xsrf` for double-submit CSRF protection.
- Revocation is persisted in PostgreSQL table `fastapi_revoked_token`, managed by
  Alembic in `backend_fastapi/`. Refresh rotation and logout insert token `jti`
  values until their original expiry.
- Browser refresh is silent on the SPA side: when an authenticated request gets
  `401`, the frontend attempts one `POST /api/v1/auth/refresh` and retries the
  original request before treating the session as logged out.
- Browser tokens also include a password-state fingerprint claim derived from
  the current password hash. If the password changes, existing FastAPI
  access and refresh tokens become invalid without waiting for normal expiry.
- Settings are environment-variable driven through `backend_fastapi/app/core/config.py`;
  `backend_fastapi/.env.local` may override local values.

## JWT de callbacks Cloud Functions (FastAPI callbacks)

Verificado en:

- `PATCH /api/v1/documents/by-function/{id}`
- `POST /api/v1/documents/generation-chunk`
- `POST /api/v1/transcription/notify-complete`

Firma: misma clave vía `get_jwt_signing_key()`.

Los tokens de callback se emiten desde `backend_fastapi` con
`iss=medical-web-app-fastapi`, `aud=medical-api-callbacks` y `purpose`
obligatorio. Los callbacks validan además los claims de recurso antes de tocar
datos clínicos: `document_id` para transcripción y `document_id + process_id`
para generación. El token SSE sigue siendo separado (`aud=medical-api-sse`,
`purpose=sse_connection`).

### Transcripción

Payload mínimo:

- `user_id` (int): médico dueño del documento
- `document_id` (int): documento a actualizar
- `exp` (datetime)
- `purpose`: `"transcription"`
- `iss`, `aud`

Emitido por: `backend_fastapi/app/core/service_jwt.py`.

### Generación de documento

Payload mínimo:

- `user_id`, `document_id`, `process_id`, `exp`, `purpose`: `"document_generation"`
- `iss`, `aud`

### SSE

Payload mínimo:

- `id_documento`, `id_usuario`, `exp`, `purpose`: `"sse_connection"`

## JWT interno del broker del copiloto

- Usado por: `backend_fastapi/app/domains/copilot/` cuando FastAPI llama a `copilot-agent-service`.
- Se firma con: `COPILOT_SERVICE_SHARED_JWT` y no con `JWT_SECRET_KEY`.
- Claims mínimos:
  - `iss`: `app-api-service`
  - `sub`: `fastapi-copilot-broker`
  - `aud`: `app-api-service`
  - `purpose`: `"copilot_internal_broker"`
  - `exp`
- Este contrato es temporal para `local` y `stg`. La deuda de migrarlo a OIDC/ID token queda registrada en [`../debt/copilot-agent-runtime.md`](../debt/copilot-agent-runtime.md).

## JWT interno de tools del copiloto

- Usado por: `copilot_agent/` cuando el runtime llama a los endpoints internos read-only de FastAPI.
- FastAPI expone `/api/internal/copilot/tools/*`; las mismas rutas también existen bajo `/api/v1/internal/...`.
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
| `COPILOT_AGENT_BASE_URL` | Base URL del `copilot-agent-service` que consume el broker FastAPI |
| `COPILOT_SERVICE_SHARED_JWT` | Secreto compartido temporal entre FastAPI y `copilot_agent` |
| `COPILOT_AGENT_AUDIENCE` | Audiencia esperada por el agent runtime |
| `COPILOT_BACKEND_AUDIENCE` | Audiencia esperada por FastAPI para las tools internas llamadas desde `copilot_agent` |
| `COPILOT_AGENT_TIMEOUT_SECONDS` | Timeout HTTP del cliente interno del copiloto. En local y broker síncrono conviene `60` para no cortar runs de edición mientras Vertex termina el draft. |
| `TRANSCRIPTION_CLOUD_FUNCTION_URL` | URL HTTP de la función de transcripción |
| `GENERATE_DOCUMENT_CLOUD_FUNCTION_URL` | URL base de la función de generación (también se acepta `GENERATE_DOCUMENT_CLOUD_FUNCTION_BASE_URL` en develop) |
