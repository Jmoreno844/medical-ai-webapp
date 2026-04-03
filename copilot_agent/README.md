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

Cuando cambien dependencias del agent, la imagen ya se sincroniza desde
`pyproject.toml + uv.lock`; toca reconstruir el contenedor para que tome esos cambios.

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

- El runtime actual usa `langgraph` + `ToolNode` con `ChatGoogleGenerativeAI(vertexai=True, ...)` y tools nativas contra Django; ya no depende de JSON prompting manual ni de `vertexai.GenerativeModel`.
- El estado del grafo persiste mensajes LangChain reales (`HumanMessage / AIMessage / ToolMessage`) y renderiza el contexto clínico con bloques XML por turno para mantener el contexto auditable y compacto.
- Las tools del graph en `app/graph/tools.py` ya usan `ToolRuntime` para recibir `state` y `tool_call_id` sin exponer ese contexto interno al modelo; esto deja el schema público de cada tool limitado a sus argumentos clínicos reales.
- Aunque el modelo usa tool calling y structured output nativos, las invocaciones hacia Google llevan `automatic_function_calling.disable=true`; así evitamos que el proveedor orchestre tools por su cuenta y mantenemos el loop clínico dentro de nuestro runtime LangGraph.
- El planner se instruye como agente secuencial estricto: puede emitir varias `read_*`/`search_*` independientes en paralelo, pero nunca mezcla lecturas dependientes con `propose_*` en el mismo turno y solo conserva una proposal de edición por vez.
- El patch drafter usa solo `json_schema` structured output y falla cerrado si Gemini no devuelve un `DraftedPatchPlan` válido; no hay fallback a `function_calling` en esa etapa para mantener el control del loop y reducir llamadas redundantes al proveedor.
- Un run `edit_document` puede terminar sin patch si el modelo devuelve una pregunta aclaratoria legítima; en ese caso el turno se completa con `final_response` y el siguiente mensaje del usuario continúa el mismo chat.
- El `thread_id` ya representa una conversación real del sidechat. Django crea uno nuevo al iniciar chat y LangGraph lo usa directamente como clave del checkpoint para preservar contexto entre mensajes del mismo hilo.
- El sidechat actual crea ese `thread_id` en el primer mensaje o cuando el usuario resetea el panel; un reload de página abre un chat nuevo.
- Los tools locales de proposal usan structured output (`DraftedPatchPlan`) para construir `patch_set_preview` sin escribir directamente el documento canónico.
- En local no hace falta crear una base separada para el copiloto; el runtime puede reutilizar `medical_web_app` porque sus tablas viven bajo nombres propios (`copilot_runs`, `copilot_run_events` y tablas del checkpointer).
- Los cambios clínicos sensibles deben seguir el camino `patch -> review -> apply` y el `apply` final seguirá viviendo en el backend principal.
