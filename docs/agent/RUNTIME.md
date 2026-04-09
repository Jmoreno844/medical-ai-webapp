# Copilot Agent — Runtime Reference

Documento de referencia de implementación para quien trabaje sobre el runtime del agente.

- Setup local y endpoints → `copilot_agent/README.md`
- Arquitectura de capas y políticas de seguridad → `docs/architecture/ai-agent-workspace.md`
- Decisiones de producto del writer → `docs/notes/copilot-clinical-writer-direction.md`
- Deuda técnica → `docs/debt/copilot-agent-runtime.md`

---

## Arquitectura de dos LLMs

El runtime usa dos LLMs separados por responsabilidad:

```
Planner (temp=0.1, max=1400 tokens)
  → Decide qué hacer: qué tool llamar, qué documento leer, o responder directo.
  → Razona sobre el mensaje del médico, el workspace y los resultados de tools previos.
  → No escribe patches.

Drafter (temp=0.0, max=3200 tokens, json_schema structured output)
  → Es invocado cuando el planner llama una propose_* tool o cuando el runtime
    entra en auto-drafting después de set_edit_plan.
  → Recibe la nota completa + contexto de soporte.
  → Emite un DraftedPatchPlan con todos los patches en una sola llamada.
  → No toma decisiones de routing ni de qué documento tocar.
```

El planner y el drafter no se llaman en paralelo. El drafter se invoca dentro de la
lógica de `propose_*` o desde una transición runtime inmediatamente posterior a
`set_edit_plan`, sin abrir una segunda decisión libre del planner.

## LangSmith local

El runtime puede emitir traces a LangSmith solo cuando `COPILOT_AGENT_ENV=local` y existen `LANGSMITH_API_KEY` + `LANGSMITH_PROJECT`. El proyecto recomendado para este servicio es `copilot-agent-local`, separado del `cloud-functions-local` usado por las Cloud Functions.

Estos traces del runtime registran metadata sanitizada del run (`run_id`, `thread_id`, estado, conteos, provider/model) y no incluyen texto clínico completo, documentos generados ni tokens. Dentro del árbol de LangSmith, los nodos LLM del runtime aparecen con nombres de rol (`Planner`, `Drafter`) en vez del nombre crudo del adapter (`ChatOpenAI`, `ChatGoogleGenerativeAI`, etc.), y además quedan etiquetados con `provider_family` para filtrar más rápido. Los nodos principales del grafo también usan nombres más semánticos (`planner_turn`, `execute_tools`, `reconcile_tool_state`, `wait_for_human_review`, `finalize_run`) para que la vista superior del trace deje más claro en qué etapa del agente estabas. Los live evals en `evals/langsmith/` siguen usando LangSmith para la matriz comparativa, pero comparten el proyecto local del servicio para mantener una sola vista del componente.

El planner tiene además un fallback defensivo para respuestas vacías del provider. Si
después de 3 reintentos sigue devolviendo un `AIMessage` sin texto ni tool calls, el
runtime evita fallar el run de forma inconsistente: cuando ya existe una lectura `full`
de un único documento y el mensaje del médico parece una edición, sintetiza una sola
`propose_replace_span(target_document_id, instruction=user_query)` para reencaminar el
flujo normal de patches. Si el pedido no parece de edición, responde con texto seguro
en lugar de dejar el run en error duro.

---

## Grafo LangGraph

```
                     ┌──────────────┐
                     │  call_model  │  ← planner decide
                     └──────┬───────┘
                            │
              ┌─────────────┼──────────────────┐
              ▼             ▼                  ▼
           tools     interrupt_for_review  finalize_response
              │
              ▼
    consolidate_tool_state
              │
     ┌────────┼───────────────┬───────────────┐
     ▼        ▼               ▼               ▼
call_model draft_patch_from_plan interrupt_for_review finalize_response
```

### Nodos

| Nodo                     | Responsabilidad                                                                                                                      |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| `call_model`             | Invoca al planner. Si hay tool_calls → tools. Si hay patch_set_preview válido + requires_human_review → interrupt. Si no → finalize. |
| `tools`                  | Executa las tools del batch actual (ToolNode). Errores se devuelven como ToolMessage al planner para que corrija.                    |
| `consolidate_tool_state` | Deriva `read_documents`, `retrieved_context`, `selected_document_ids` del batch de resultados. Entonces re-routea.                   |
| `draft_patch_from_plan`  | Si `set_edit_plan` ya dejó `next_required_action='draft_patch_set'` y las precondiciones están listas, invoca al drafter directamente. |
| `interrupt_for_review`   | Pausa el grafo. Espera `review_result` externo (`approve` / `reject`). LangGraph interrupt.                                          |
| `apply_patch`            | Placeholder — el apply real ocurre en Django, no aquí.                                                                               |
| `finalize_response`      | Construye el `final_response` del run.                                                                                               |

### Routing

`_route_after_model`:

- `tool_calls` presentes → `"tools"`
- `patch_set_preview` válido + `requires_human_review=True` → `"interrupt_for_review"`
- otherwise → `"finalize_response"`

`_route_after_tools`:

- `iteration_count >= max_iterations` → `"finalize_response"`
- `patch_set_preview` válido + `requires_human_review=True` → `"interrupt_for_review"`
- `run_error` presente → `"finalize_response"`
- `next_required_action='draft_patch_set'` + target/full note listos → `"draft_patch_from_plan"`
- otherwise → `"call_model"`

### Límites de iteración

```python
max_iterations: int = 6        # default en CopilotState
max_patch_operations: int = 1  # base local; set_edit_plan lo eleva dinámicamente por scope clínico
```

---

## Estado del grafo (campos clave)

El estado completo es `CopilotState` en `app/graph/state.py`. Los campos relevantes para entender el runtime:

### Contexto del workspace (entra por el primer mensaje)

| Campo                 | Tipo                 | Descripción                                                                                                         |
| --------------------- | -------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `workspace_index`     | `dict`               | Vista ligera del workspace: documento activo, abiertos, writable, versiones y opcionalmente `content_markdown` pre-seedeado por el frontend. Entra desde Django en el primer turno. |
| `available_documents` | `list[dict]`         | Documentos disponibles en el workspace. Se va enriqueciendo con lecturas. Merge inteligente por `document_id`.      |
| `document_summaries`  | `dict[doc_id, dict]` | Summaries de documentos leídos. Merge por doc_id, score por completitud.                                            |

### Artefactos de lectura (acumulados en el run)

| Campo            | Tipo                 | Descripción                                                                                  |
| ---------------- | -------------------- | -------------------------------------------------------------------------------------------- |
| `document_reads` | `list[dict]`         | Resultados de `read_document(mode=*)`. Incluye `content` cuando `mode="full"`.               |
| `read_documents` | `list[dict]`         | Vista derivada de `document_reads` enriquecida por summaries. Usada por el planner.          |
| `read_spans`     | `list[dict]`         | Resultados de `read_document_span`. Keyed por (doc_id, start_offset, end_offset, exactText). |
| `context_view`   | `dict \| None`       | Resultado de `build_context_view`. Contexto estructurado del encounter.                      |
| `search_results` | `list[dict]`         | Resultados de `search_documents`.                                                            |
| `patch_history`  | `dict[doc_id, list]` | Patches aplicados previamente al documento target. Entra desde `read_patch_history`.         |

### Estado del run actual

| Campo                    | Tipo          | Descripción                                                                        |
| ------------------------ | ------------- | ---------------------------------------------------------------------------------- |
| `iteration_count`        | `int`         | Iteraciones del loop principal. Cap en `max_iterations`.                           |
| `patch_operations_count` | `int`         | Cuántas propose\_\* tools se han ejecutado. Cap en `max_patch_operations`.         |
| `current_plan_step`      | `str`         | Última acción del planner (`"start"`, `"call_tool"`, `"respond"`).                 |
| `run_error`              | `str \| None` | Si hay error irrecuperable, se setea aquí y el run termina en `finalize_response`. |
| `last_tool_error`        | `str \| None` | Error del último batch de tools. Se pasa al planner para que corrija.              |
| `next_required_action`   | `str \| None` | Señal runtime. Hoy usa `draft_patch_set` para continuar automáticamente tras `set_edit_plan`. |
| `planned_target_document_id` | `str \| None` | Documento target congelado por `set_edit_plan` cuando el runtime lo puede inferir con seguridad. |

### Artefactos del patch set

| Campo                   | Tipo           | Descripción                                                                                       |
| ----------------------- | -------------- | ------------------------------------------------------------------------------------------------- |
| `target_document_id`    | `str \| None`  | ID del documento target del patch set.                                                            |
| `target_document_title` | `str \| None`  | Título del documento target.                                                                      |
| `base_version`          | `int \| None`  | Versión del documento en el momento de la lectura. Django valida conflictos contra esta versión.  |
| `patch_set_preview`     | `dict \| None` | El patch set completo listo para review. Enviado a Django para persisitir como `CopilotPatchSet`. |
| `patch_preview`         | `dict \| None` | Mirror del primer patch del set (compatibilidad con frontend legacy).                             |
| `requires_human_review` | `bool`         | Si es True y hay `patch_set_preview` válido, el grafo pausa en `interrupt_for_review`.            |

### Estado de review

| Campo            | Tipo          | Descripción                                                                                                  |
| ---------------- | ------------- | ------------------------------------------------------------------------------------------------------------ |
| `review_result`  | `str \| None` | `"approve"` / `"reject"`. Entra cuando el médico responde en el frontend y Django llama `/runs/{id}/resume`. |
| `review_comment` | `str \| None` | Comentario opcional del médico al aprobar o rechazar.                                                        |

### Reset entre runs

Cuando Django inicia un nuevo run en el mismo thread (misma conversación), `_reset_transient_run_state()` limpia todos los artefactos del run anterior (reads, spans, patches, errores) pero conserva `messages` y la historia del hilo LangGraph. Esto evita que un patch propuesto en turno anterior contamine el siguiente turno.

### Pre-seed desde frontend (`workspace_index.documents[].content_markdown`)

Si el frontend envía `content_markdown` para un documento `ai_writable`, `_reset_transient_run_state()` lo convierte en una lectura `mode="full"` antes del primer turno del planner.

Eso permite que el planner llame `propose_*` en el turno 1 sin `read_document(...)`, pero trae dos invariantes importantes:

1. el contenido debe representar el estado canónico que el médico ve realmente
2. la lectura pre-seedeada necesita `content_hash` para que el patch set tenga `base_hash`

El runtime ya no depende de que el frontend mande ese hash. Si falta en `workspace_index`, el agente calcula `sha256(content_markdown)` al pre-seedear la lectura full. Esto mantiene consistente el contrato con Django, que valida conflictos de apply usando `base_hash`.

En otras palabras: el pre-seed del frontend reemplaza la lectura remota, pero no puede omitir la metadata que vuelve aplicable el patch set.

---

## Herramientas disponibles

### Surface de lectura

| Tool                                                           | Cuándo usarla                                                                                                                                           |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `read_document(document_id, mode)`                             | Lectura de documento. `mode="summary"` para orientarse; `mode="excerpt"` para chequeo ligero; `mode="full"` para cambios amplios o propagación clínica. |
| `read_document_summary(document_id)`                           | Sólo resumen conciso. Útil para saber de qué trata un documento antes de decidir si leerlo completo.                                                    |
| `read_document_span(document_id, exact_text, ...)`             | Lectura focalizada de una región del documento. También resuelve anchors para cambios locales.                                                          |
| `build_context_view()`                                         | Recupera hechos estructurados del encounter: paciente, médico, encounter, documentos abiertos. No lee contenido de los documentos.                      |
| `list_open_documents()`                                        | Lista documentos abiertos en el workspace.                                                                                                              |
| `list_encounter_documents()`                                   | Lista todos los documentos del encounter, incluyendo no-abiertos.                                                                                       |
| `search_documents(query, max_results, allowed_document_types)` | Búsqueda semántica por contenido clínico. Solo para términos clínicos específicos. Nunca para metadata.                                                 |
| `read_patch_history(document_id, limit)`                       | Últimos patches aplicados al documento. Útil antes de proponer nuevos cambios.                                                                          |

### Surface de escritura (propose)

Todas las tools de propose siguen el mismo patrón:

1. Validan precondiciones (el documento existe, es `ai_writable`, y fue leído previamente con span o full).
2. Invocan al drafter (`planner.draft_patch_preview(...)`).
3. Construyen y validan el `patch_set_preview`.
4. Setean `requires_human_review=True` → el grafo pausará en `interrupt_for_review`.

Cuando la lectura previa proviene del pre-seed de `workspace_index` en vez de `read_document`, el builder del patch set puede derivar `base_hash` de dos maneras:

- usar `summary_payload.content_hash` / `span_payload.content_hash` si ya existen
- fallback: si el `summary_payload` es en realidad una lectura `mode="full"` con `content`, calcular `sha256(content)` localmente

Ese fallback evita que una `propose_*` tool termine como `tool_result` exitoso pero sin `patch_set_preview` válido solo porque el frontend evitó el round-trip de lectura.

Todas aceptan un parámetro opcional `instruction: str | None`. El planner debe usarlo para
describir exactamente qué texto cambiar y cómo. Si el planner tiene múltiples reemplazos
para un mismo documento, **debe consolidarlos todos en una sola llamada** usando `instruction`
en lugar de llamar la tool varias veces (el filtro `_filter_parallel_tool_calls` descargaría
las llamadas adicionales silenciosamente). El drafter lee `instruction` como `<requested_instruction>`
en su contexto XML y la prioriza sobre la inferencia desde el mensaje original del médico.
Las propose tools también aceptan `affected_sections: list[str] | None` para cambios locales
directos donde el planner ya conoce la sección destino pero no quiere pasar por `set_edit_plan`.
Cuando llegan esas secciones, el runtime construye un scope mínimo local y activa el mismo
guardrail semántico del drafter.
Para `edit_scope in {propagation, reinterpretation}` o para cualquier `propose_*` con
`affected_sections`, el runtime valida además que el
`DraftedPatchPlan` cubra todas las `affected_sections` del `edit_plan` y que cada patch
declare `section`. Si el drafter devuelve un subconjunto parcial, la tool falla cerrada y
no abre review humana con un patch set incompleto.

Ese guardrail también aplica cuando el planner fija `affected_sections` en un
`edit_scope="local"` para follow-ups ambiguos resueltos por contexto conversacional
previo. Si el scope declarado contiene una sola sección y el drafter devuelve patches
para secciones extra, el runtime falla cerrado y obliga a regenerar el patch set dentro
del scope correcto.

| Tool                                                          | Operación del drafter                            |
| ------------------------------------------------------------- | ------------------------------------------------ |
| `propose_replace_span(target_document_id, instruction?, affected_sections?)`      | Reemplaza un span existente por contenido nuevo. |
| `propose_insert_after_span(target_document_id, instruction?, affected_sections?)` | Inserta contenido nuevo después de un span.      |
| `propose_insert_before(target_document_id, instruction?, affected_sections?)`     | Inserta contenido nuevo antes de un anchor.      |
| `propose_delete_span(target_document_id, instruction?, affected_sections?)`       | Borra un span del documento.                     |

La tool llama al drafter con `requested_tool_name` y `requested_tool_instruction` como pistas. El drafter puede emitir múltiples patches en una sola llamada (`patches: list[DraftedPatch]`).

> `propose_create_document()` existe en el código pero siempre retorna error. No está habilitada.

### Regla de separación read/write

El planner **nunca debe combinar** `read_*` + `propose_*` en el mismo turno (mismo batch de tool_calls). Primero lee, luego propone. Esta regla está en el system instruction del planner y es un invariante de seguridad.

---

## Schema del patch set

El `patch_set_preview` que se emite al finalizar una propose tool:

```python
{
  "patch_set_id": str,               # UUID del set
  "target_document_id": str,
  "target_document_title": str,
  "target_selection_reason": str,    # ej. "llm_target_document_id, active_document"
  "base_version": int,               # Versión del doc en el momento de lectura
  "base_hash": str,
  "rationale": str | None,           # Explicación general del cambio
  "document_preview_after": str | None,
  "source_context_document_ids": list[str],
  "patches": [
    {
      "patch_id": str,               # UUID individual del patch
      "operation_type": str,         # "replace_span" | "insert_before" | "insert_after_span" | "delete_span"
      "order_index": int,
      "anchor": {
        "exactText": str,            # PRIMARIO: 3-8 palabras únicas, sin newlines
        "prefixText": str | None,    # Texto inmediatamente antes de exactText
        "suffixText": str | None,    # Texto inmediatamente después de exactText
        "startOffset": int | None,   # Ayuda secundaria
        "endOffset": int | None      # Ayuda secundaria
      },
      "content_preview": str,        # Texto nuevo a insertar/reemplazar
      "before_preview": str | None,
      "after_preview": str | None,
      "rationale": str,
      "clinical_impact": str | None  # "cosmetic" | "factual" | "clinical" (P1 futuro)
    }
  ]
}
```

### Requisito de `base_hash`

`base_hash` no es opcional en la práctica del runtime actual. Si falta, el patch set no se considera válido y el run puede terminar en `completed` sin `patch_proposed` ni `review_required`, aunque sí exista un `tool_result` de `propose_*`.

Eso suele significar una de estas dos cosas:

- no había ninguna lectura válida (`summary` / `full` / `span`) del documento target
- había lectura pre-seedeada full, pero sin `content_hash` y sin fallback de contenido

Los cambios recientes del runtime cubren explícitamente el segundo caso.

Django recibe este payload, resuelve los anchors a offsets reales en el documento canónico, persiste un `CopilotPatchSet` + `CopilotPatch` por cada entrada en `patches`, y marca los patches como `pending` o `conflicted` según el resultado de la resolución.

---

## Estrategia de anchors

Los patches no dependen de offsets exactos para ser aplicados porque los offsets se vuelven obsoletos si el documento cambia entre que el agente leyó y cuando Django aplica.

| Campo anchor                | Rol                                                                                              |
| --------------------------- | ------------------------------------------------------------------------------------------------ |
| `exactText`                 | Primario — Django busca este substring en el documento actual                                    |
| `prefixText`                | Desambiguación — si `exactText` aparece más de una vez, `prefixText` reduce falsas coincidencias |
| `suffixText`                | Desambiguación — igual que `prefixText` pero hacia adelante                                      |
| `startOffset` / `endOffset` | Secundarios — ayudan cuando el texto no se encuentra pero los offsets siguen siendo válidos      |

El drafter debe usar `exactText` de 3-8 palabras, de una sola línea, único en el documento. No incluir `\n` en `exactText`.

---

## Evals live del runtime

La surface de evals live del agente busca comparar el comportamiento del workflow real,
no solo el prompt aislado. Por eso los evals principales reutilizan:

- el mismo `LangChainCopilotPlanner`
- las mismas instrucciones del planner y del drafter
- el mismo schema clínico (`ClinicalPlan`, `DraftedPatchPlan`)
- la misma surface de propose tools y sus validaciones runtime

### Matriz actual de providers

- `gpt-5.4-mini`
- `gpt-5.4-nano`
- `gemini-2.5-flash`
- `gemini-2.5-flash-lite`
- `gemini-3-flash-preview`
- `gemini-3.1-flash-lite-preview`
- `claude-haiku-4-5`

Los providers Gemini no comparten exactamente la misma región:

- `gemini-2.5*` corre en `us-east1`
- `gemini-3* preview` corre en `global`

La región correcta viaja dentro de la propia matriz de providers para que un run mixto
mantenga el endpoint correcto por modelo y no dependa de un único `GCP_REGION` global.

### Provider del runtime productivo

El runtime real ya no queda fijo a Gemini. Se configura por `.env` con:

- `COPILOT_LLM_PROVIDER_FAMILY=openai|google|anthropic`
- `COPILOT_PLANNER_MODEL`
- `COPILOT_PATCH_MODEL`

Overrides opcionales por componente:

- `COPILOT_PLANNER_PROVIDER_FAMILY`
- `COPILOT_PATCH_PROVIDER_FAMILY`
- `COPILOT_PLANNER_GOOGLE_LOCATION`
- `COPILOT_PATCH_GOOGLE_LOCATION`

Reglas actuales:

- si no se overridea nada, planner y drafter usan el mismo provider/modelo
- el default del repo ahora es `openai + gpt-5.4-mini`
- `VERTEX_MODEL` queda como fallback legacy cuando el provider efectivo es `google`
- para OpenAI y Anthropic, las credenciales se leen desde `OPENAI_API_KEY` y `ANTHROPIC_API_KEY`

### Comandos útiles

Desde `copilot_agent/`:

```bash
make evals-e2e COUNT=5
make evals-e2e EXACT=3
make evals-e2e-gemini-2-5 COUNT=5
make evals-e2e-gemini-preview COUNT=5
make evals-e2e-openai COUNT=5
make evals-e2e-anthropic COUNT=5
make evals-e2e-model MODEL=google-gemini-3-flash-preview EXACT=3
```

`COUNT=5|10|15` recorta la matriz a los primeros N casos clínicos compartidos.
`EXACT=3` corre solo el caso número 3 de la lista compartida y tiene prioridad sobre `COUNT`.
Si además quieres exactamente un solo pytest case, combínalo con `MODEL=...`.

### Qué mirar en LangSmith para comparar modelos

Los evals e2e publican en `inputs` y `outputs` campos pensados para filtrar sin abrir cada trace:

- `model_name`
- `patch_model_name`
- `provider`
- `provider_family`
- `provider_region`
- `selected_document_ids`
- `failure_stage`

Además publican feedbacks comparables entre modelos:

- `correct_first_tool`
- `single_tool_call`
- `edit_scope_exact_match`
- `impact_level_exact_match`
- `section_coverage`
- `runtime_valid`
- `patches_per_expected_section`
- `planner_latency_s`
- `drafter_latency_s`

Para elegir “qué modelo es mejor para nuestros casos”, el mejor filtro inicial no es el texto libre del trace sino:

1. `runtime_valid = 0`
2. `failure_stage != ok`
3. baja `section_coverage`
4. latencia alta con `runtime_valid = 1`

### Casos thread-like vs replay real

El primer caso live ya es más parecido a un sidechat real porque incluye varios documentos
seleccionados, un target note y contexto clínico de soporte que cambia análisis y plan.

Eso sigue siendo un estado sintético controlado, no un replay literal de un `thread_id` real.

Si se quiere probar el runtime completo “como ocurrió en producción”, la siguiente capa no es
agregar más texto al caso actual sino crear `thread replay evals` con fixtures anonimizadas que
incluyan:

- `messages` previos del hilo
- `workspace_index`
- `selected_document_ids`
- `read_documents`
- `tool_results` previos
- `planner_decisions` previos
- `patch_history` si existía

La idea es ejecutar el grafo compilado completo, no solo planner→drafter, para medir mejor:

- vacíos del planner tras un `read_document(full)`
- loops innecesarios de lectura
- errores de mezcla `read_*` + `propose_*`
- patch sets incompletos bajo contexto largo del thread

Esa surface complementa a la matriz e2e actual; no la reemplaza.

## Flujos típicos

### Caso 1: Mensaje simple ("Traduce esta frase al inglés")

```
call_model
  → lee workspace_index + summaries
  → planner: llama read_document_span(exactText="...")

tools + consolidate
  → span leído

call_model
  → planner: llama propose_replace_span(target_document_id)

tools (propose_replace_span)
  → drafter emite 1 patch: replace_span
  → patch_set_preview construido

interrupt_for_review
  → médico revisa y aprueba

finalize_response
```

**LLM calls:** 2 (planner ×2) + 1 (drafter) = 3 total

---

### Caso 2: Propagación clínica ("El paciente tiene 10 semanas de embarazo, reescribe la nota")

```
call_model
  → planner: llama read_document(mode="full")

tools + consolidate
  → nota completa leída

call_model
  → planner: identifica reinterpretation clínica
  → llama propose_replace_span(target_document_id)
  → [futuro P0] emite structured_plan con affected_sections

tools (propose_replace_span)
  → drafter recibe nota completa + affected_sections
  → emite 5 patches en una sola llamada (DraftedPatchPlan.patches: list)
  → patch_set_preview con 5 patches construido

interrupt_for_review
  → médico ve patches agrupados por sección
  → acepta o rechaza individualmente

finalize_response
```

**LLM calls:** 2 (planner ×2) + 1 (drafter) = 3 total  
**Patches:** 5 en un solo JSON del drafter  
**Iteraciones:** 2 del loop

---

### Caso 3: Mensaje conversacional ("¿Qué diagnósticos tiene la paciente?")

```
call_model
  → planner: llama build_context_view() o read_document(mode="summary")

tools + consolidate

---

## Evaluaciones locales

El runtime ahora tiene dos superficies de eval separadas del `pytest` determinista:

- `copilot_agent/evals/langsmith/` contiene tests `pytest` marcados como `live_llm` y `langsmith`. Ejecutan el planner y el drafter reales contra Vertex con casos clínicos dummy/de-identified. Por defecto quedan fuera del `pytest` normal para evitar costo accidental.
- `copilot_agent/evals/promptfoo/` contiene una suite de prompt regressions que reutiliza esos mismos casos mediante un provider Python local. La idea es validar contratos de salida y regresiones de prompt sin duplicar la lógica del runtime ni mantener un segundo stack de auth.
- `copilot_agent/evals/shared/clinical_cases.py` es la única fuente de verdad para los casos clínicos dummy usados por ambas superficies.

Los live evals deben seguir siendo local-first y nunca deben usar notas o transcripciones reales. Si cambias el contrato del planner/drafter, actualiza los casos compartidos, las aserciones de promptfoo y cualquier feedback/logging relevante de LangSmith en el mismo cambio.
  → contexto / summary leído

call_model
  → planner: responde directo sin proponer patches

finalize_response
```

**LLM calls:** 1-2 (planner) = no hay drafter  
**No hay patch_set_preview, no hay interrupt**

---

## Invariantes de seguridad

- El agente **nunca escribe directamente** al documento canónico. Solo emite `patch_set_preview`. Django hace el apply.
- Si el drafter emite un `DraftedPatchPlan` vacío (`patches=[]`) o inválido, la propose tool retorna un error al planner y el run termina en `finalize_response` con `run_error`.
- Si Vertex falla o devuelve JSON inválido, el run cierra en `failed`. No hay fallback a heurísticas.
- Los datos clínicos en documentos son tratados como **datos**, no como instrucciones ejecutables. El system instruction del planner lo refuerza explícitamente para proteger contra prompt injection.
- `read_*` y `propose_*` nunca se combinan en el mismo batch de tool_calls.

---

## Archivos clave

```
copilot_agent/app/
├── planner.py              → CopilotPlanner, DraftedPatchPlan, DraftedPatch, PlannerDecision
├── graph/
│   ├── workflow.py         → build_clinical_copilot_graph(), grafo LangGraph
│   ├── state.py            → CopilotState, funciones de merge por campo
│   ├── nodes.py            → nodos del grafo, routing, reset de run state
│   └── tools.py            → herramientas, _propose_patch, _build_patch_set_preview_payload
└── llm/
    ├── instructions.py     → system instructions del planner y del drafter
    └── context_rendering.py → render_turn_context(), render_patch_input()
```
