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
Planner (temp=0.1, max=700 tokens)
  → Decide qué hacer: qué tool llamar, qué documento leer, o responder directo.
  → Razona sobre el mensaje del médico, el workspace y los resultados de tools previos.
  → No escribe patches.

Drafter (temp=0.0, max=1600 tokens, json_schema structured output)
  → Solo es invocado cuando el planner llama una propose_* tool.
  → Recibe la nota completa + contexto de soporte.
  → Emite un DraftedPatchPlan con todos los patches en una sola llamada.
  → No toma decisiones de routing ni de qué documento tocar.
```

El planner y el drafter no se llaman en paralelo. El drafter es invocado dentro de la
lógica de `propose_*` tools, que son ejecutadas por el ToolNode del grafo.

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
     ┌────────┼─────────────────────┐
     ▼        ▼                     ▼
call_model  interrupt_for_review  finalize_response
```

### Nodos

| Nodo                     | Responsabilidad                                                                                                                      |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| `call_model`             | Invoca al planner. Si hay tool_calls → tools. Si hay patch_set_preview válido + requires_human_review → interrupt. Si no → finalize. |
| `tools`                  | Executa las tools del batch actual (ToolNode). Errores se devuelven como ToolMessage al planner para que corrija.                    |
| `consolidate_tool_state` | Deriva `read_documents`, `retrieved_context`, `selected_document_ids` del batch de resultados. Entonces re-routea.                   |
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
- otherwise → `"call_model"`

### Límites de iteración

```python
max_iterations: int = 6        # default en CopilotState
max_patch_operations: int = 1  # default — a revisar para casos multipatch (ver P0 en writer-direction.md)
```

---

## Estado del grafo (campos clave)

El estado completo es `CopilotState` en `app/graph/state.py`. Los campos relevantes para entender el runtime:

### Contexto del workspace (entra por el primer mensaje)

| Campo                 | Tipo                 | Descripción                                                                                                         |
| --------------------- | -------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `workspace_index`     | `dict`               | Vista ligera del workspace: documento activo, abiertos, writable, versiones. Entra desde Django en el primer turno. |
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

| Tool                                            | Operación del drafter                            |
| ----------------------------------------------- | ------------------------------------------------ |
| `propose_replace_span(target_document_id)`      | Reemplaza un span existente por contenido nuevo. |
| `propose_insert_after_span(target_document_id)` | Inserta contenido nuevo después de un span.      |
| `propose_insert_before(target_document_id)`     | Inserta contenido nuevo antes de un anchor.      |
| `propose_delete_span(target_document_id)`       | Borra un span del documento.                     |

La tool llama al drafter con `requested_tool_name` como pista. El drafter puede emitir múltiples patches en una sola llamada (`patches: list[DraftedPatch]`).

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
