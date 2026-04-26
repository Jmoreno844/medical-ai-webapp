# Copilot Agent Service

Servicio dedicado para el copiloto clínico basado en LangGraph.

## Rol

- ejecutar el runtime del copiloto fuera del backend principal
- mantener threads/runs/checkpoints del agente
- emitir eventos estructurados del run
- proponer patches, nunca aplicar cambios clínicos críticos por su cuenta

## Boundary

- el frontend **no** debe hablar directo con este servicio
- FastAPI actúa como broker seguro hacia el frontend
- la fuente de verdad clínica sigue en el backend principal
- este servicio solo expone endpoints internos de runs/resume/status/events
- para leer contexto clínico real, este runtime consume tools read-only internas expuestas por FastAPI

## Local dev

1. Levanta PostgreSQL local y aplica `uv --project backend_fastapi run alembic upgrade head`
2. Copia `.env.example` a `.env.local`
3. Por defecto, el agent reutiliza la misma base local `medical_web_app` del backend para no exigir una DB extra en local
4. Si corres el agent en Docker, `BACKEND_INTERNAL_BASE_URL` debe apuntar al backend del host como `http://host.docker.internal:8001` y FastAPI debe estar levantado con `0.0.0.0:8001`
5. Corre:

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

- El runtime actual usa `langgraph` + `ToolNode` con `ChatGoogleGenerativeAI(vertexai=True, ...)` y tools nativas contra FastAPI; ya no depende de JSON prompting manual ni de `vertexai.GenerativeModel`.
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
- El `thread_id` ya representa una conversación real del sidechat. FastAPI crea uno nuevo al iniciar chat y LangGraph lo usa directamente como clave del checkpoint para preservar contexto entre mensajes del mismo hilo.
- El `WorkspaceIndex` no solo aporta IDs: el planner recibe también un working set ligero de documentos abiertos/seleccionados para reconocer títulos/tipos antes de llamar tools y no quedar sesgado por el turno anterior.
- Cuando un patch se aprueba o rechaza, el runtime escribe una respuesta sintética de cierre dentro del mismo thread checkpoint. Así el siguiente turno ve que el flujo anterior ya quedó resuelto y puede priorizar el pedido nuevo del médico.
- El sidechat actual crea ese `thread_id` en el primer mensaje o cuando el usuario resetea el panel; un reload de página abre un chat nuevo.
- Los tools locales de proposal usan structured output (`DraftedPatchPlan`) para construir `patch_set_preview` sin escribir directamente el documento canónico.
- En local no hace falta crear una base separada para el copiloto; el runtime puede reutilizar `medical_web_app` porque sus tablas viven bajo nombres propios (`copilot_runs`, `copilot_run_events` y tablas del checkpointer).
- Los cambios clínicos sensibles deben seguir el camino `patch -> review -> apply` y el `apply` final seguirá viviendo en el backend principal.

## Evaluaciones LLM locales

El repo ahora separa tres capas de verificación:

- `uv run pytest tests -q` para regresiones deterministas sin provider real.
- `uv run pytest -m live_llm evals/langsmith -q` para evals locales con planner/drafter reales y tracking opcional en LangSmith.
- `npx promptfoo@latest eval -c evals/promptfoo/promptfooconfig.yaml` para regresiones de prompt y contrato usando los mismos casos clínicos dummy.

### LangSmith pytest

1. Sincroniza dependencias de dev:

```bash
uv sync --group dev
```

2. Guarda el mínimo de entorno en `.env.local` o expórtalo manualmente. Los helpers de eval cargan `.env.local` y luego `.env` automáticamente si existen:

```bash
GCP_PROJECT_ID=tu-proyecto
GCP_REGION=us-east1
VERTEX_MODEL=gemini-2.5-flash
LANGSMITH_API_KEY=tu-api-key
LANGSMITH_PROJECT=copilot-agent-local
LANGSMITH_TEST_SUITE=copilot-agent-local-live
```

3. Corre los evals live:

```bash
make -C copilot_agent evals-live
```

Para una comparacion cualitativa de razonamiento clinico sobre una misma nota base y prompts incrementalmente mas duros, usa:

```bash
make -C copilot_agent evals-reasoning
make -C copilot_agent evals-reasoning EXACT=2
```

Ese runner vive en `evals/langsmith/test_live_clinical_reasoning.py` y hoy compara `gemini-3-flash-preview`, `claude-haiku-4-5` y `gpt-4o-mini`. Puedes activarlos o desactivarlos cambiando los booleans `ENABLE_GEMINI_3_FLASH_PREVIEW`, `ENABLE_CLAUDE_HAIKU_4_5` y `ENABLE_GPT_4_MINI` al inicio del archivo. Los casos estan separados en `evals/shared/clinical_reasoning_cases.py` para que luego puedas crecer la bateria sin mezclar datos clinicos con el runner.

Si ejecutas `make -C copilot_agent` sin target, verás una ayuda corta con los comandos disponibles en vez de lanzar tests.

Si quieres correrlos sin subir resultados a LangSmith, usa `make -C copilot_agent evals-live-no-track`.

Si no defines `LANGSMITH_PROJECT`, LangSmith usa su proyecto por defecto. Para no mezclar estos runs con otros experimentos, conviene fijarlo en `.env.local`.

Para la matriz e2e multi-provider:

```bash
make -C copilot_agent evals-e2e COUNT=5
make -C copilot_agent evals-e2e EXACT=3
make -C copilot_agent evals-e2e-gemini-2-5 COUNT=5
make -C copilot_agent evals-e2e-gemini-preview COUNT=5
make -C copilot_agent evals-e2e-openai COUNT=5
make -C copilot_agent evals-e2e-anthropic COUNT=5
make -C copilot_agent evals-e2e-model MODEL=google-gemini-3-flash-preview EXACT=3
```

`COUNT` recorta la matriz a los primeros N casos. Los providers Gemini 2.5 usan `us-east1`; los previews Gemini 3 usan `global`.
`EXACT` selecciona un único caso por índice 1-based y tiene prioridad sobre `COUNT`.
Para correr exactamente un solo pytest case, úsalo junto con `MODEL=...`.

### Promptfoo

Promptfoo usa un provider Python local (`evals/promptfoo/provider.py`) para reutilizar `LangChainCopilotPlanner`, las instrucciones reales y el mismo shape de contexto del runtime. La diferencia es que ahora inyecta adapters LangChain por provider para comparar el mismo workflow contra OpenAI, Gemini y Anthropic sin duplicar prompts.

Modelos iniciales de la matriz:

- `gpt-5.4-mini`
- `gpt-5.4-nano`
- `gemini-2.5-flash`
- `gemini-2.5-flash-lite`
- `gemini-3-flash-preview`
- `gemini-3.1-flash-lite-preview`
- `claude-haiku-4-5`

Credenciales necesarias:

- Gemini: reutiliza `GCP_PROJECT_ID` + credenciales Vertex ya usadas por el runtime. Para los previews `gemini-3*` conviene usar `global`; para `gemini-2.5*` puede mantenerse `us-east1`.
- OpenAI: exporta `OPENAI_API_KEY`.
- Anthropic: exporta `ANTHROPIC_API_KEY`.

```bash
export PROMPTFOO_PYTHON=$(command -v python)
npx promptfoo@latest eval -c evals/promptfoo/promptfooconfig.yaml
```

### Smoke test de modelos

Antes de correr la matriz clínica completa, puedes validar credenciales y model IDs con una sola llamada por modelo:

```bash
make -C copilot_agent evals-smoke
```

Ese smoke test no evalúa calidad clínica; solo confirma que cada provider responde con el model ID configurado y una salida mínima utilizable.

Los casos compartidos viven en `evals/shared/clinical_cases.py`. El set inicial incluye 15 casos de dificultad alta, todos dummy/de-identified, mezclando propagacion factual y reinterpretacion clinica para aproximarse mejor al sidechat real. El pytest live y promptfoo leen la misma fuente para que una regresion de prompt se pueda comparar contra la evaluacion trazada del runtime real.

Los evals e2e registran en LangSmith campos iniciales visibles para comparar modelos sin abrir cada trace: `model_name`, `patch_model_name`, `provider`, `provider_family`, `provider_region`, `selected_document_ids` y `failure_stage`.

Si la intención es emular un `thread_id` real completo, la siguiente capa recomendada es agregar evals de replay del grafo completo con fixtures anonimizadas del hilo, no solo seguir creciendo el caso sintético base.

`pytest` por defecto ya no mira los scripts exploratorios `test_*.py` en la raíz del servicio; la configuración oficial apunta a `tests/` y `evals/langsmith/`.
