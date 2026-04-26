# Backend Django -> FastAPI Migration Plan

Este plan define una migracion completa del backend central de Django Ninja a
FastAPI sin romper los contratos clinicos existentes con la SPA, Cloud
Functions, GCS, PostgreSQL y `copilot_agent`.

## Resumen

- Migrar por fases con una API FastAPI en paralelo, manteniendo la compatibilidad
  de rutas actuales hasta que frontend, Cloud Functions y copilot esten en la
  nueva superficie.
- Usar PostgreSQL como fuente de verdad existente; no recrear datos ni reescribir
  migraciones historicas. El cambio de ORM/migraciones debe ser controlado y
  verificable.
- Reemplazar sesion Django por JWTs seguros para navegador y servicios:
  access token corto, refresh rotativo, cookies `HttpOnly`, `Secure`,
  `SameSite`, CSRF para requests mutantes y JWTs separados por proposito para
  callbacks, SSE y copilot.
- Adoptar FastAPI async donde haya I/O real: DB async, HTTP interno async,
  SSE, GCS, Cloud Tasks y llamadas a servicios. Evitar marcar como async código
  que siga usando clientes bloqueantes.
- Introducir versionado explicito bajo `/api/v1`, con aliases temporales para
  las rutas legacy mientras se migra el frontend.

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
- `admin` de Django no debe bloquear la migracion. Si aun se necesita una UI
  administrativa, se reemplazara por una herramienta explicita despues de portar
  los endpoints clinicos.
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
    Functions, SSE, Django/FastAPI -> copilot y copilot -> backend tools.
  - Validar siempre `iss`, `aud`, `purpose`, `exp`, `iat` y claims de dominio
    como `document_id`, `process_id`, `user_id`, `run_id` o `thread_id`.
  - No registrar tokens, documentos completos, transcripciones completas ni
    prompts clinicos en logs.

- Versionado y contratos:
- Congelar los payloads actuales antes de portar endpoints.
- Preservar comentarios útiles del código Django al portar módulos a FastAPI,
  especialmente los que documenten contratos, seguridad, compatibilidad legacy o
  límites clínicos; evitar copiar comentarios que solo narren sintaxis.
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
   - Agregar `Makefile`/Docker targets paralelos sin tocar el deploy de Django.
   - Publicar `/api/v1/health` y OpenAPI versionado.

3. **Modelo de datos y migraciones**
   - Mapear tablas existentes a SQLAlchemy manteniendo nombres reales de tablas,
     columnas, indices y constraints.
   - Introducir Alembic con baseline del schema actual, sin regenerar historia
     Django.
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

7. **Cutover y retiro de Django**
   - Ejecutar ambos backends en staging y comparar respuestas para rutas criticas.
   - Migrar `VITE_API_URL`, Cloud Functions callbacks y copilot tools a FastAPI.
   - Retirar rutas legacy, dependencias Django, settings Django y migrations
     Django solo cuando Alembic y tests cubran el schema activo.

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
- El sistema no debe aceptar una migracion como completa hasta que Django deje de
  ser requerido para auth, migraciones, admin operativo, callbacks, SSE y copilot
  tools.
