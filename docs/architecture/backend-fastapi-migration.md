# FastAPI Backend Cutover

Este documento deja el estado final del cutover del backend central a FastAPI,
sin depender del antiguo monolito para runtime ni migraciones.

## Resumen

- `backend_fastapi/` es la API principal. Las rutas públicas viven bajo
  `/api/v1/*`.
- Alembic crea el schema completo en bases nuevas mediante
  `alembic/baseline/baseline_clinical_v1.sql` y revisiones posteriores.
- Usar JWTs seguros para navegador y servicios:
  access token corto, refresh rotativo, cookies `HttpOnly`, `Secure`,
  `SameSite`, CSRF para requests mutantes y JWTs separados por proposito para
  callbacks, SSE y copilot.
- Usar FastAPI async donde haya I/O real: DB async, HTTP interno async,
  SSE, GCS, Cloud Tasks y llamadas a servicios. Evitar marcar como async código
  que siga usando clientes bloqueantes.
- El monolito Django fue retirado del repo; cualquier rollback debe venir de un
  artefacto/branch histórico, no de `main`.

## Arquitectura Objetivo

- `backend_fastapi/` sera la nueva app ASGI con capas claras:
  `api/` para routers versionados, `core/` para config/security/logging,
  `domains/` para logica de negocio, `db/` para sesiones/modelos/migraciones,
  `schemas/` para Pydantic v2 y `integrations/` para GCS, Cloud Tasks, Cloud
  Functions y copilot.
- La API publica del navegador vivira en `/api/v1/*`; las rutas legacy `/api/*`
  se mantendran solo como compatibilidad temporal o redireccion interna durante
  la transicion.
- SQLAlchemy 2.0 async + Alembic sera el stack recomendado para la migracion
  final. La fase intermedia puede leer el schema existente, pero no debe generar
  migraciones destructivas ni renombrar tablas de forma implicita.
- Si se necesita una UI administrativa, se reemplazara por una herramienta
  explicita en FastAPI o fuera del repo.
- Redis queda fuera de la primera migración. SSE conserva un hub en memoria
  equivalente al actual; por eso Cloud Run debe mantenerse en `max-instances=1`
  con `session-affinity=true` hasta una fase futura con Redis/Pub/Sub.

## Cambios Clave

- Auth de navegador:
  - `POST /api/v1/auth/login` emite cookies `access_token` y `refresh_token`.
  - `POST /api/v1/auth/refresh` rota refresh token y revoca el anterior.
  - `POST /api/v1/auth/logout` revoca refresh token y limpia cookies.
  - `GET /api/v1/auth/me` reemplaza `/api/auth/me` y `/api/auth/me/data`.
  - CSRF se conserva para mutaciones autenticadas por cookie.

- JWTs de servicio:
- Mantener secretos/audiencias separados: navegador, callbacks Cloud
    Functions, SSE, FastAPI -> copilot y copilot -> backend tools.
  - Validar siempre `iss`, `aud`, `purpose`, `exp`, `iat` y claims de dominio
    como `document_id`, `process_id`, `user_id`, `run_id` o `thread_id`.
  - No registrar tokens, documentos completos, transcripciones completas ni
    prompts clinicos en logs.

- Versionado y contratos:
- Mantener payloads clínicos revisables y OpenAPI actualizado.
- Preservar comentarios útiles que documenten contratos, seguridad,
  compatibilidad o límites clínicos; evitar comentarios que solo narren sintaxis.
- Para cambios no compatibles, crear DTOs nuevos en `/api/v1` y adaptar el
  frontend una ruta a la vez.
  - Mantener OpenAPI como artefacto revisable y usarlo para contract tests.

- Async y background work:
  - Usar `asyncpg`, `httpx.AsyncClient`, stream responses async y clientes async
    cuando existan.
  - Sustituir el thread local de generacion documental por una cola/runner
    explicita. Cloud Tasks o Pub/Sub son las opciones preferidas en GCP.
  - Cloud Functions siguen siendo Gemini-facing; FastAPI conserva la autoridad
    transaccional y de apply clinico.

## Fases de Implementacion

1. **Inventario y tests de contrato**
   - Enumerar todas las rutas actuales, codigos de estado, payloads y auth.
   - Agregar tests de contrato para auth, encounters, documents, templates,
     patients, callbacks, SSE, GCS upload URLs, transcription kickoff y copilot.
   - Capturar fixtures minimas de PostgreSQL sin datos clinicos reales.

2. **Scaffold FastAPI**
   - Crear `backend_fastapi/` con FastAPI, Pydantic v2, settings tipados,
     logging JSON, CORS, security headers, tracing OpenTelemetry y healthchecks.
   - Agregar Docker targets y workflow de deploy propios.
   - Publicar `/api/v1/health` y OpenAPI versionado.

3. **Modelo de datos y migraciones**
   - Mapear tablas existentes a SQLAlchemy manteniendo nombres reales de tablas,
     columnas, indices y constraints.
   - Introducir Alembic con baseline del schema actual.
   - Portar primero queries read-only, luego writes transaccionales.

4. **Auth y seguridad**
   - Implementar hashing compatible para passwords existentes o una migracion
     controlada de hashes.
   - Implementar JWT browser cookies, CSRF, refresh rotation, revocation store,
     rate limiting de login y proteccion de brute force.
   - Portar y endurecer JWTs de callbacks, SSE y copilot con validacion de
     audiencia/proposito.

5. **Dominios clinicos**
   - Portar en orden: users/auth, patients, templates, encounters, documents,
     generative_ai callbacks/kickoff, copilot broker/tools.
   - En cada dominio, mover primero schemas y servicios, luego routers, luego
     actualizar frontend/Cloud Functions si cambia la ruta.
   - Mantener `content_json` y `content_markdown` sincronizados en un unico
     servicio de documentos.

6. **Streaming e integraciones**
   - Reimplementar SSE con `StreamingResponse` y hub en memoria.
   - Migrar signed URLs GCS, Cloud Tasks, llamadas a Cloud Functions y cliente
     copilot a clientes async.
   - Alinear tracing `webapp -> FastAPI -> Cloud Functions -> FastAPI`.

7. **Estado final**
   - `VITE_API_URL`, Cloud Functions callbacks y copilot tools apuntan a FastAPI.
   - El deploy automático a Cloud Run publica `backend_fastapi` (imagen
     `fastapi-backend`).
   - Django no vive en `main`.

### Propiedad del schema post-cutover (stg+)

- Bases de datos **nuevas (vacías)**: solo `alembic upgrade head` en
  `backend_fastapi/`; la revisión `0001` aplica el DDL congelado en
  `alembic/baseline/baseline_clinical_v1.sql` (auth/contenttypes, tablas
  de dominio, copilot, `fastapi_revoked_token`). `backend_fastapi/scripts/migration_smoke_staging.sh`
  hace eso por defecto. Regenerar el SQL en entornos controlados con
  `backend_fastapi/scripts/build_alembic_baseline_sql.py`.
- Verificación de paridad: `backend_fastapi/scripts/verify_alembic_schema_parity.sh`
  contra una base histórica de referencia y una base creada solo con Alembic.
- Las **nuevas** migraciones de tablas compartidas van en **Alembic**; los
  cambios de schema ya no usan migraciones Django.

### Puerta de verificación usada para retirar Django (repo)

- Esquema: prueba con PostgreSQL vacío: `uv --project backend_fastapi run alembic upgrade head`.
- Paridad: `backend_fastapi/scripts/verify_alembic_schema_parity.sh` (referencia
  histórica + candidato Alembic).
- Tests: `uv --project backend_fastapi run ruff check .`, `uv --project backend_fastapi run pytest -q`; `npm --prefix webapp run build`. Cloud Functions: `python -m pytest cloud_functions/functions/tests`. Smoke
  staging: login, encuentro, URL firmada, transcripción, SSE documentos, copilot
  si el entorno está disponible.

## Plan de Pruebas

- Unit tests por servicio de dominio: permisos por medico, validaciones de
  payload, sync `content_json`/`content_markdown`, expiracion de audio y apply de
  patches.
- Integration tests con PostgreSQL real para transacciones, constraints,
  migraciones Alembic y compatibilidad de hashes de password.
- Contract tests HTTP para cada ruta legacy y su reemplazo `/api/v1`.
- Security tests para CSRF, cookies, refresh rotation, revocacion, expiracion,
  `aud`, `iss`, `purpose`, replay de callbacks y rate limiting.
- SSE tests para conexion, ping, desconexion, delivery via Redis y permisos por
  documento y comportamiento con instancia única.
- End-to-end smoke en staging: login, crear encuentro, signed upload URL,
  transcripcion, generacion documental, editor save, copilot run, patch review y
  apply.

## Decisiones y Defaults

- Default recomendado para navegador: JWT en cookies `HttpOnly`, no localStorage.
- Default recomendado para DB: SQLAlchemy async + Alembic, manteniendo schema
  existente.
- Default recomendado para versionado: `/api/v1` con compat temporal `/api`.
- Default para la primera fase SSE: hub en memoria y Cloud Run con una instancia.
- Redis/Pub/Sub queda como migración futura cuando se necesiten múltiples réplicas.
- Default recomendado para migracion: strangler pattern por dominio, no big bang.
- El sistema no debe aceptar un cambio de schema sin Alembic, pruebas y docs.
