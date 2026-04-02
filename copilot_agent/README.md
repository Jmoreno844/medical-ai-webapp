# Copilot Agent Service

Servicio dedicado para el copiloto clínico basado en LangGraph.

## Rol

- ejecutar el runtime del copiloto fuera del backend principal
- mantener threads/runs/checkpoints del agente
- emitir eventos estructurados del run
- proponer patches, nunca aplicar cambios clínicos críticos por su cuenta

## Boundary

- el frontend **no** debe hablar directo con este servicio
- Django actúa como broker seguro hacia el frontend
- la fuente de verdad clínica sigue en el backend principal
- este servicio solo expone endpoints internos de runs/resume/status/events
- para leer contexto clínico real, este runtime consume tools read-only internas expuestas por Django

## Local dev

1. Levanta PostgreSQL local con `make -C backend db-up`
2. Copia `.env.example` a `.env.local`
3. Por defecto, el agent reutiliza la misma base local `medical_web_app` del backend para no exigir una DB extra en local
4. Corre:

```bash
cp copilot_agent/.env.example copilot_agent/.env.local
docker compose -f copilot_agent/docker-compose.yml up --build
```

Healthcheck:

```bash
curl http://localhost:8090/healthz
```

## Endpoints internos

- `POST /internal/copilot/runs`
- `POST /internal/copilot/runs/{run_id}/resume`
- `GET /internal/copilot/runs/{run_id}`
- `GET /internal/copilot/runs/{run_id}/events`

Todos los endpoints internos, salvo `/healthz`, esperan `Authorization: Bearer <jwt>`
firmado con `COPILOT_SERVICE_SHARED_JWT`.

## Notas

- La implementación inicial deja el grafo, los tools y el checkpointer claramente delimitados, aunque Django todavía no consuma estos endpoints en producción.
- En local no hace falta crear una base separada para el copiloto; el runtime puede reutilizar `medical_web_app` porque sus tablas viven bajo nombres propios (`copilot_runs`, `copilot_run_events` y tablas del checkpointer).
- Los cambios clínicos sensibles deben seguir el camino `patch -> review -> apply` y el `apply` final seguirá viviendo en el backend principal.
