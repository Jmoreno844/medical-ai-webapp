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
- `planner.py` actua como fachada ligera del runtime del LLM; los renderers XML y las instrucciones viven en `app/llm/` para que el hardening de prompts y el armado del contexto se puedan probar por separado sin tocar la orquestacion.
- Las tools del graph en `app/graph/tools.py` ya usan `ToolRuntime` para recibir `state` y `tool_call_id` sin exponer ese contexto interno al modelo; esto deja el schema público de cada tool limitado a sus argumentos clínicos reales.
- La surface de lectura distingue entre `read_document(mode="summary" | "excerpt" | "full")` y `read_document_span`: la primera sirve para leer el documento como unidad y la segunda para anclar cambios locales o resolver texto ambiguo.
- La surface pública de patches del runtime ya cubre `propose_replace_span`, `propose_insert_after_span`, `propose_insert_before` y `propose_delete_span`; el backend sigue siendo el dueño del apply final y de la resolución real de anchors.
- Aunque el modelo usa tool calling y structured output nativos, las invocaciones hacia Google llevan `automatic_function_calling.disable=true`; así evitamos que el proveedor orchestre tools por su cuenta y mantenemos el loop clínico dentro de nuestro runtime LangGraph.
- El planner se instruye para permitir batches de tools `non-write` independientes en paralelo; `propose_*` sigue siendo estrictamente secuencial y nunca debe mezclarse con lecturas en el mismo turno.
- Las tools `non-write` devuelven solo deltas mergeables al estado. Después de cada batch, el nodo `consolidate_tool_state` recompone `read_documents`, `retrieved_context`, selección efectiva y compat fields de búsqueda para evitar `INVALID_CONCURRENT_GRAPH_UPDATE` en LangGraph.
- El patch drafter usa solo `json_schema` structured output y falla cerrado si Gemini no devuelve un `DraftedPatchPlan` válido; no hay fallback a `function_calling` en esa etapa para mantener el control del loop y reducir llamadas redundantes al proveedor.
- El planner y el drafter tratan transcripciones, notas, spans y facts recuperados como datos clinicos, no como instrucciones ejecutables; si el contenido recuperado es ambiguo o insuficiente, el runtime debe pedir mas contexto o fallar cerrado en vez de inventar cambios.
- Los anchors del writer flow se basan primero en contenido (`exactText`, `prefixText`, `suffixText`) y usan offsets solo como ayuda secundaria. Esto vuelve más robusto el apply cuando el documento cambió entre lectura y revisión.
- Un run `edit_document` puede terminar sin patch si el modelo devuelve una pregunta aclaratoria legítima; en ese caso el turno se completa con `final_response` y el siguiente mensaje del usuario continúa el mismo chat.
- El `thread_id` ya representa una conversación real del sidechat. Django crea uno nuevo al iniciar chat y LangGraph lo usa directamente como clave del checkpoint para preservar contexto entre mensajes del mismo hilo.
- El `WorkspaceIndex` no solo aporta IDs: el planner recibe también un working set ligero de documentos abiertos/seleccionados para reconocer títulos/tipos antes de llamar tools y no quedar sesgado por el turno anterior.
- Cuando un patch se aprueba o rechaza, el runtime escribe una respuesta sintética de cierre dentro del mismo thread checkpoint. Así el siguiente turno ve que el flujo anterior ya quedó resuelto y puede priorizar el pedido nuevo del médico.
- El sidechat actual crea ese `thread_id` en el primer mensaje o cuando el usuario resetea el panel; un reload de página abre un chat nuevo.
- Los tools locales de proposal usan structured output (`DraftedPatchPlan`) para construir `patch_set_preview` sin escribir directamente el documento canónico.
- En local no hace falta crear una base separada para el copiloto; el runtime puede reutilizar `medical_web_app` porque sus tablas viven bajo nombres propios (`copilot_runs`, `copilot_run_events` y tablas del checkpointer).
- Los cambios clínicos sensibles deben seguir el camino `patch -> review -> apply` y el `apply` final seguirá viviendo en el backend principal.
