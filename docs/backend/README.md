# Backend

El `backend/` es la API central del sistema. Orquesta autenticación, encuentros, documentos, SSE y la comunicación con Cloud Functions.

## Qué leer aquí

- [`database.md`](database.md) — modelo de datos, ERD y notas sobre PostgreSQL / SQLite.
- [`auth-and-jwt.md`](auth-and-jwt.md) — sesión Django, JWT de usuario, JWT de callbacks y SSE.
- [`logging.md`](logging.md) — política de logging de Django por entorno.
- [`tracing.md`](tracing.md) — OpenTelemetry, Jaeger local y Cloud Trace en GCP.
- [`secrets-and-environments.md`](secrets-and-environments.md) — variables de entorno y settings modules.
- [`docker.md`](docker.md) — Dockerfiles, Compose y scripts de soporte.

## Mapa rápido del código

- `backend/apps/` — dominios de negocio (`users`, `encounters`, `documents`, `patients`, `templates`, `generative_ai`).
- `backend/config/settings/` — `base`, `develop`, `stg`, `test`, `production` y utilidades de logging.
- `backend/utils/` — autenticación JWT y helpers compartidos.

## Cómo se relaciona con el resto

- Recibe requests del frontend con sesión Django.
- Emite JWT de vida corta para Cloud Functions.
- Publica eventos SSE para transcripción y generación en tiempo real.
