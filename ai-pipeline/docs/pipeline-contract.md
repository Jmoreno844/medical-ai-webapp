# AI Pipeline — contrato end-to-end

Referencia de la harness R&D en `ai-pipeline/`: qué hace cada etapa, versiones de prompt por defecto, esquemas de entrada/salida y cómo se conectan.

**No es el pipeline de producción** (`backend_fastapi`, workers Cloud Run). Es el sandbox local para iterar prompts y plantillas.

---

## Vista general

```mermaid
flowchart TB
  subgraph transcript["Rama transcript"]
    T[TranscriptCase<br/>turns[]]
    F[filtering v002]
    C[clustering v002<br/>+ repair v001 opcional]
    CL[classification v004]
    G[generation v003]
    T --> F --> C --> CL --> G
  end

  subgraph context["Rama contexto (paralela)"]
    DN[nota médico]
    DOC[PDF / texto]
    SD[split_doctor_items · código]
    TR[triage v001]
    AN[approved_note_spans · código]
    BS[build_spans documentos · código]
    FS[filter_spans v002]
    MERGE[merge]
    CS[cluster_spans v002]
    CC[classify_clusters v002]
    SA[section_adapter v003]
    DN --> SD --> TR
    TR --> AN
    DOC --> BS
    AN --> MERGE
    BS --> FS --> MERGE
    MERGE --> CS --> CC --> SA
  end

  TMPL[(ClinicalTemplate<br/>templates/*.json)]
  SC[section_context<br/>dict section_id → texto]

  TMPL --> CL
  TMPL --> CC
  TMPL --> G
  TMPL --> SA
  SA --> SC
  SC --> G
```

**Fusión:** `generation` recibe por sección `clusters[]` (transcript) + `context` (brief del `section_adapter` vía `section_context`). Solo **generation** produce prosa final de la nota; el adapter prepara contexto externo compacto (`brief`).

---

## Mapa de tipos I/O

Leyenda de columnas:

| Columna | Significado |
|---------|-------------|
| **Input (dominio)** | Tipo Python / estructura que consume el paso desde upstream |
| **User al modelo** | Formato del mensaje `user` enviado al LLM (`—` si no hay LLM) |
| **Output parseado** | Modelo Pydantic o forma JSON tras `parse_*_result()` |
| **Salida downstream** | Qué recibe el siguiente paso tras post-proceso |

### Rama transcript

| Etapa | LLM | Input (dominio) | User al modelo | Output parseado | Salida downstream |
|-------|-----|-----------------|----------------|-----------------|-------------------|
| Turn catalog | No | `TranscriptCase` | — | `list[{turn_id, speaker, text}]` | catálogo para filtering |
| filtering | Sí | turn catalog | v001: JSON `{turns}` · v002: `<transcript>` + JSON | `FilteringResult` → `{drop_turn_ids: int[]}` | transcript filtrado, `turn_id` renumerados |
| clustering | Sí | turn catalog filtrado | v001: JSON `{turns}` · v002: `<transcript>` + JSON | `ClusteringResult` → `{clusters[{topic_label, turn_ids}], unassigned_turn_ids?}` | clusters enriquecidos con `turns[]` |
| clustering repair | Sí | clusters + turnos faltantes | JSON `{existing_clusters, missing_turns}` | `{assignments[], unassigned_turn_ids}` | clusters reparados (mismos `topic_label`) |
| classification | Sí | `ClusterCase[]` + `ClinicalTemplate` | v004: bloques · v003: system+JSON · v001/v002: JSON | `{assignments[{cluster_id, section_ids[]}]}` o v001 `{section_ids[]}` | jobs por sección (transcript) |
| generation | Sí | sección + clusters + `context?` + plantilla | JSON `{section, template_guidelines, clusters, context}` | `{section_id, content: str}` | markdown por sección |

### Rama contexto

| Etapa | LLM | Input (dominio) | User al modelo | Output parseado | Salida downstream |
|-------|-----|-----------------|----------------|-----------------|-------------------|
| split / build / merge | No | nota, PDF, texto | — | `DoctorItem[]`, `Span[]` pool | `Span[]` ids `"1"`…`"N"` |
| triage | Sí | `DoctorItem[]` + manifest (docs + secciones) | JSON `{session_id, manifest, items[]}` | `TriageResult` → `{directives[], content_ids[], drop_ids[]}` | filtra qué items/spans construir; directives por scope |
| filter_spans | Sí | `Span[]` de **documentos** + fechas (sin directives) | v001/v002: JSON (sin `date_hint` en spans) | `FilterSpansResult` → `{drop_ids: str[]}` | `document_directive_filter` → merge con `approved_note_spans` |
| document_directive_filter | Parcial | `Span[]` documentales + `Directive[]` documentales | selector v001: `{directive, spans}` | `keep_ids[]` / ignore determinístico | spans documentales finales antes de clustering |
| cluster_spans | Sí | `Span[]` filtrados | v001: JSON `{spans}` · v002: `<spans>` + `<span id>` | `SpanCluster[]` → `{id, title, span_ids[]}` | clusters con `date_hints` propagados |
| classify_clusters | Sí | `SpanCluster[]` + `Span[]` + plantilla + fechas | v001: JSON monolítico · v002: bloques semánticos | `ClassifyClustersResult` → `{assignments[{cluster_id, section_ids[]}]}` | `build_adapter_jobs()` → `{section_id: [cluster_id]}` |
| section_adapter | Sí | job por sección + clusters + spans | v003: `<section>`, `<guidelines>`, `<input_json>` · v002: JSON | `SectionAdapterResult` → `{section_id, brief}` | `section_context: dict[str, str]` (brief por sección) |

### Payload LLM vs tipos de dominio

| Concepto | Dónde vive | Notas |
|----------|------------|-------|
| `TranscriptCase` | `common/transcripts.py` | Fixture JSON en `cases/transcripts/` |
| `ClinicalTemplate` | `common/templates.py` | `templates/*.json`; nunca se manda entera al LLM en v004 |
| `Span` / `SpanCluster` | `common/context_spans.py` | `Span.id` numérico string; `date_hint` solo en dominio, no en filter/cluster user |
| Turn catalog | `build_turn_catalog()` | Proyección plana del transcript; `turn_id: int` |
| `section_context` | export adapter | `dict[section_id, brief]`; input opcional de generation v003 como `context` |

---

## Versiones de prompt por defecto (UI / `ui/discovery.py`)

| Etapa | Archivo prompt | Default | Otras versiones |
|-------|----------------|---------|-----------------|
| filtering | `filtering/prompts/filtering_prompt_v001.py` (o `filtering_v001.txt`) | **v002** | v001 (.txt) |
| clustering | `clustering/prompts/clustering_prompt_v001.py` (o `clustering_v001.txt`) | **v002** | v001 (.txt) |
| clustering repair | `clustering/prompts/clustering_repair_prompt_v001.py` (o `clustering_repair_v001.txt`) | **v002** | v001 (.txt); solo si faltan turnos tras clustering |
| classification | `classification/prompts/classification_prompt_v001.py` (o `classification_v003.txt`) | **v004** | v001, v002, v003 (.txt) |
| generation | `generation/prompts/generation_v003.txt` | **v003** | v001, v002 |
| triage | `context_pipeline/triage/prompts/triage_prompt_v001.py` | **v001** | — |
| filter_spans | `context_pipeline/filter_spans/prompts/filter_spans_prompt_v001.py` (o `filter_spans_v001.txt`) | **v002** | v001 (.txt) |
| cluster_spans | `context_pipeline/cluster_spans/prompts/cluster_spans_prompt_v001.py` (o `cluster_spans_v001.txt`) | **v002** | v001 (.txt) |
| classify_clusters | `context_pipeline/classify_clusters/prompts/classify_clusters_prompt_v001.py` (o `classify_clusters_v001.txt`) | **v002** | v001 (.txt) |
| section_adapter | `context_pipeline/section_adapter/prompts/adapter_prompt_v001.py` (o `.txt` v001/v002) | **v003** | v001, v002 (.txt) |

Los módulos `.py` usan sufijo `*_prompt_v001.py` (primer artefacto Python del paso). La clave de versión en UI/registry (`v002`, `v003`, `v004`) sigue alineada con el historial de `.txt` y no con el nombre del archivo.

Plantillas disponibles: `minimal_outpatient_v001`, `outpatient_general_v001`, `consulta_estructurada_v001`.

---

## Patrón de prompts v004+ (`.py` + bloques model-facing)

A partir de **classification v004** el harness soporta prompts versionados en módulos Python además de `.txt`:

| Pieza | Ubicación | Rol |
|-------|-----------|-----|
| Registro | `common/prompt_registry.py` | `PY_PROMPTS[step][version]` → módulo importable |
| Bloques | `common/prompt_blocks.py` | `render_block(tag, body)`, `join_blocks([...])` |
| Prompt paso | `<step>/prompts/<step>_prompt_vNNN.py` | `SYSTEM_PROMPT`, `render_user_payload(...)`, `output_schema(...)` |
| Discovery | `ui/discovery.py` | `list_prompt_versions()` = union `.txt` + `.py` |

**Contrato módulo `.py`:**
- `SYSTEM_PROMPT: str` — reglas fijas (va en `system` del LLM).
- `render_user_payload(...) -> str` — datos variables en bloques `<tag>...</tag>` en el `user`.
- `output_schema(...) -> dict` — JSON Schema estricto para Structured Outputs (opcional).

**Structured Outputs:** `call_llm_detailed(..., output_schema=...)` en `common/providers.py`. Anthropic recibe `output_config.format.type=json_schema`; OpenAI/Groq/Gemini lo ignoran por ahora (siguen con `json_object`).

**Sin thinking visible:** el system prompt pide procedimiento interno; salida solo JSON.

---

## Plantilla clínica (`templates/*.json`)

Modelo: `common/templates.py` → `ClinicalTemplate`.

### Top-level

| Campo | Uso |
|-------|-----|
| `id`, `name`, `document_kind` | Identidad y tipo de documento |
| `classification.guidelines` | Reglas globales de clasificación (v003 system; v004 bloque user; v001/v002 user JSON) |
| `generation.guidelines` | Reglas globales de redacción → `template_guidelines` en generation |

### Por sección (`TemplateSection`)

| Campo | Uso |
|-------|-----|
| `section_id`, `heading`, `description` | Identidad y descripción en todos los payloads de plantilla |
| `include` | Qué va en la sección (v002+; texto libre, admite `\n` y viñetas) |
| `boundaries` | Qué no va / límites frente a otras secciones (opcional) |
| `classification.guidelines` | Guideline crudo por sección (v001 lleno; v002 vacío → migra a include/boundaries) |
| `generation.guidelines` | Idem para generación |

### Composición de guidelines (código, no en JSON del LLM)

`compose_section_guidelines(raw, include, boundaries)`:

- Si `include` y `boundaries` vacíos → devuelve `raw` (backward-compat v001).
- Si hay contenido → `"Incluye:\n{include}"` + `"\n\nLímites:\n{boundaries}"` + `raw` si existe.

Se aplica en:

- `to_classification_payload()` / `to_generation_payload()` → clave `guidelines`
- `format_template_for_classification_system()` (classification **v003**)
- `classification/prompts/classification_prompt_v001.py` → bloque `<allowed_sections>` (classification **v004**)
- `render_section_adapter_payload()` → clave `section_guidelines` (prompt **v002**)

### Quién consume la plantilla

| Etapa | ¿Usa plantilla? | Cómo llegan include/boundaries |
|-------|-----------------|--------------------------------|
| filtering, clustering | No | — |
| classification v004 | Sí | User: bloques `<allowed_sections>` con `to_classification_payload()` |
| classification v003 | Sí | System: bloque `PLANTILLA ACTIVA` con guidelines compuestos |
| classification v001/v002 | Sí | User: `template.sections[].guidelines` compuesto vía `to_classification_payload()` |
| classify_clusters v001 | Sí | User JSON: `to_generation_payload()` por sección |
| classify_clusters v002 | Sí | User bloques: `to_classification_payload()` por sección |
| section_adapter v002 | Sí | User: `section_guidelines` compuesto |
| section_adapter v001 | Sí | Solo `section_description` (sin guidelines) |
| generation | Sí | User: `section` + `template_guidelines` |

---

## Fixtures y tipos compartidos

| Recurso | Ubicación | Rol |
|---------|-----------|-----|
| Transcript | `cases/transcripts/` + `cases/index.json` | `TranscriptCase` con `chunks[].turns[]` |
| Cluster cases | `cases/cluster/` | Clusters pre-armados para debug de classification |
| Context cases | `cases/context/` | Nota médico, PDFs, `encounter_date`, `document_date` |
| Spans / directives | `common/context_spans.py` | Modelos de la rama contexto |

### Turn catalog (código)

`build_turn_catalog(transcript)` → `[{turn_id, speaker, text}, ...]`

Usado por filtering y clustering como user payload base.

---

## Rama transcript

### 0. Entrada — transcript (sin LLM)

| | |
|---|---|
| **LLM** | No |
| **Input (dominio)** | `TranscriptCase` → `transcript_json.chunks[].turns[]` |
| **User al modelo** | — |
| **Output (código)** | `build_turn_catalog()` → `list[{turn_id: int, speaker: str, text: str}]` |
| **Salida downstream** | turn catalog hacia filtering |

---

### 1. Filtering

| | |
|---|---|
| **LLM** | Sí |
| **Input (dominio)** | turn catalog |
| **Output parseado** | `FilteringResult` → `{drop_turn_ids: int[]}` |
| **Post-proceso** | `apply_filtering_to_transcript()`; renumera `turn_id` |
| **Salida downstream** | transcript filtrado → clustering |

| Versión | System | User | Structured output |
|---------|--------|------|-------------------|
| **v001** | `filtering_v001.txt` | JSON `{ "turns": [...] }` vía `render_user_payload()` | No |
| **v002** (default) | `filtering/prompts/filtering_prompt_v001.py` → `SYSTEM_PROMPT` | Bloque `<transcript>` con JSON de turns | Sí (`drop_turn_ids` con enum de turn_id conocidos) |

#### v002 — user payload

```
<transcript>
{
  "turns": [
    { "turn_id": 0, "speaker": "PACIENTE", "text": "..." }
  ]
}
</transcript>
```

**Output LLM:**

```json
{ "drop_turn_ids": [3, 17] }
```

**Post-proceso:** `apply_filtering_to_transcript()` elimina turnos y **renumera** `turn_id` desde 0.

**No usa plantilla.**

---

### 2. Clustering

| | |
|---|---|
| **LLM** | Sí |
| **Input (dominio)** | turn catalog (transcript ya filtrado) |
| **Output parseado** | `ClusteringResult` → `{clusters[{topic_label, turn_ids: int[]}], unassigned_turn_ids?}` |
| **Post-proceso** | enriquecimiento export con `turns[]` por cluster |
| **Salida downstream** | `ClusterCase[]` → classification |

| Versión | System | User | Structured output |
|---------|--------|------|-------------------|
| **v001** | `clustering_v001.txt` | JSON `{ "turns": [...] }` vía `render_user_payload()` | No |
| **v002** (default) | `clustering/prompts/clustering_prompt_v001.py` → `SYSTEM_PROMPT` | Bloque `<transcript>` con JSON de turns | Sí (`clusters[].turn_ids` con enum de turn_id conocidos) |

#### v002 — user payload

```
<transcript>
{
  "turns": [
    { "turn_id": 0, "speaker": "medico", "text": "..." }
  ]
}
</transcript>
```

**Output LLM:**

```json
{
  "clusters": [
    { "topic_label": "dolor_toracico", "turn_ids": [1, 2, 5] }
  ]
}
```

v002 no incluye `unassigned_turn_ids` en el schema estructurado; el parser sigue aceptándolo si el modelo lo devuelve.

**Enriquecimiento export:** añade `turns` con texto por cluster.

**Repair (opcional):** si faltan turnos, `clustering_repair_v002.py` (default) o `clustering_repair_v001.txt` con `existing_clusters[]` + `missing_turns[]` → `assignments` + `unassigned_turn_ids`. No crea clusters nuevos. v002 usa structured output con enum de `topic_label` y `turn_id` conocidos.

#### clustering repair v002

| | |
|---|---|
| **LLM** | Sí (opcional; solo si faltan turnos) |
| **Input (dominio)** | `existing_clusters[]` + `missing_turns[]` |
| **Output parseado** | `{assignments[{turn_id, topic_label}], unassigned_turn_ids: int[]}` |
| **Salida downstream** | clusters reparados (sin nuevos `topic_label`) |

| | |
|---|---|
| **System** | `clustering/prompts/clustering_repair_prompt_v001.py` → `SYSTEM_PROMPT` |
| **User** | JSON con `existing_clusters[]` + `missing_turns[]` |
| **Structured output** | Sí (`assignments[].turn_id`, `assignments[].topic_label`, `unassigned_turn_ids`) |

**Puente → classification:** `clusters_from_clustering_result()` crea `ClusterCase` por cluster:

```json
{
  "cluster_id": "{session_id}_{topic_label}",
  "topic_label": "...",
  "turns": [{ "turn_id", "speaker", "text" }]
}
```

**No usa plantilla.**

---

### 3. Classification

| | |
|---|---|
| **LLM** | Sí |
| **Input (dominio)** | `ClusterCase[]` (`cluster_id`, `topic_label`, `turns[]`) + `ClinicalTemplate` |
| **Output parseado** | v001: `{section_ids[]}` · v002+: `{assignments[{cluster_id, section_ids[]}]}` |
| **Salida downstream** | asignación cluster → `section_id`(s) para generation |

| Versión | System prompt | User payload | Structured output |
|---------|---------------|--------------|-------------------|
| **v001** | Solo archivo `.txt` base | `cluster` + `template` completo (`to_classification_prompt_payload()`) | No |
| **v002** | Solo archivo `.txt` base | `clusters[]` + `template` completo | No |
| **v003** | Base + **`PLANTILLA ACTIVA`** (`format_template_for_classification_system`) | `clusters[]` + **`template_ref`** compacto (JSON) | No |
| **v004** (default) | **`classification/prompts/classification_prompt_v001.py`** → `SYSTEM_PROMPT` | Bloques model-facing (ver abajo) | Sí (`output_schema` con enum de section_ids) |

#### v004 — system

Módulo `classification/prompts/classification_prompt_v001.py` → constante `SYSTEM_PROMPT` con secciones `# Identity`, `# Task`, `# Rules`, `# Classification priority`, `# Fallback heuristics`, `# Output contract`. La plantilla **no** va en el system.

#### v004 — user payload (bloques, no JSON monolítico)

```
<template_ref>
id: consulta_estructurada_v001
allowed_section_ids: ["identificacion", "motivo_consulta", ...]
</template_ref>

<template_classification_guidelines>
{template.classification.guidelines}
</template_classification_guidelines>

<allowed_sections>
<section id="signos_vitales">
Title: Signos vitales
Description: ...
Classification guidelines: Incluye:...
</section>
...
</allowed_sections>

<clusters>
[
  {
    "cluster_id": "case1_dolor_toracico",
    "topic_label": "dolor_toracico",
    "turns": [...]
  }
]
</clusters>
```

Proyección de clasificación: `section.to_classification_payload()["guidelines"]` (sin guidelines de generation).

#### v004 — output schema (API)

```json
{
  "type": "object",
  "properties": {
    "assignments": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "cluster_id": { "type": "string" },
          "section_ids": {
            "type": "array",
            "items": { "type": "string", "enum": ["motivo_consulta", "..."] }
          }
        },
        "required": ["cluster_id", "section_ids"],
        "additionalProperties": false
      }
    }
  },
  "required": ["assignments"],
  "additionalProperties": false
}
```

#### v003 — system (campos añadidos por código)

Texto append tras el prompt base:

```
PLANTILLA ACTIVA
id: ...
name: ...
document_kind: ...

Guías globales de clasificación:
{template.classification.guidelines}

Secciones permitidas (usa solo estos section_id):

### {section_id}
heading: ...
description: ...
classification_guidelines: {compose_section_guidelines(...)}
```

#### v003 — user payload

```json
{
  "clusters": [
    {
      "cluster_id": "case1_dolor_toracico",
      "topic_label": "dolor_toracico",
      "turns": [{ "turn_id": 0, "speaker": "PACIENTE", "text": "..." }]
    }
  ],
  "template_ref": {
    "id": "consulta_estructurada_v001",
    "allowed_section_ids": ["identificacion", "motivo_consulta", "..."]
  }
}
```

#### v001/v002 — user payload (sección template)

```json
{
  "template": {
    "id": "...",
    "name": "...",
    "guidelines": "{classification global}",
    "sections": [
      {
        "section_id": "...",
        "heading": "...",
        "description": "...",
        "guidelines": "Incluye:\n...\n\nLímites:\n..."
      }
    ]
  }
}
```

**Output LLM (v002/v003 batch):**

```json
{
  "assignments": [
    {
      "cluster_id": "case1_dolor_toracico",
      "section_ids": ["motivo_consulta", "enfermedad_actual"]
    }
  ]
}
```

**Output LLM (v001 single cluster):**

```json
{ "section_ids": ["motivo_consulta"] }
```

---

### 4. Generation

| | |
|---|---|
| **LLM** | Sí (una llamada por sección) |
| **Input (dominio)** | `section` + `clusters[]` asignados + `context: str` (adapter) + `ClinicalTemplate` |
| **User al modelo** | JSON `{section, template_guidelines, clusters, context}` |
| **Output parseado** | `{section_id: str, content: str}` |
| **Salida downstream** | markdown ensamblado (`render_generated_section_markdown`) |

| Versión | Fuente contexto externo | User payload |
|---------|-------------------------|--------------|
| **v001** | No | `section`, `template_guidelines`, `clusters[]` |
| **v002** | `enrichment_claims[]` (legacy claims) | Igual + claims estructurados |
| **v003** (default) | `context` (string del section_adapter) | `section`, `template_guidelines`, `clusters[]`, `context` |

#### User payload (v003, por sección)

```json
{
  "section": {
    "section_id": "estudios_y_resultados",
    "heading": "...",
    "description": "...",
    "guidelines": "Incluye:\n...\n\nLímites:\n..."
  },
  "template_guidelines": "{template.generation.guidelines}",
  "clusters": [
    {
      "cluster_id": "case1_labs",
      "topic_label": "laboratorios",
      "turns": [...]
    }
  ],
  "context": "En registro previo consta hemoglobina 9.2 g/dL..."
}
```

- `clusters` puede ser `[]` si solo hay contexto.
- `context` puede ser `""` si solo hay clusters.
- Al menos uno debe existir (`plan_section_generation`).

**Output LLM:**

```json
{
  "section_id": "estudios_y_resultados",
  "content": "Exámenes realizados: ..."
}
```

**Post-proceso:** `render_generated_section_markdown()` puede anteponer `## {heading}` al ensamblar el documento.

**Ejecución:** una llamada LLM por sección con clusters y/o context (paralelizable).

---

## Rama contexto

Orquestación: `context_pipeline/session.py`.

### Pasos solo código (sin LLM)

| Paso | Función | Input (dominio) | Output (dominio) |
|------|---------|-----------------|------------------|
| Split nota | `split_doctor_items()` | `str` (nota médico) | `tuple[DoctorItem[], is_pasted]` |
| Build spans (nota) | `doctor_items_to_spans()` o `build_spans_from_text()` si `is_pasted` | `DoctorItem[]` + `content_ids` o nota pegada | `approved_note_spans` (no pasan por `filter_spans`) |
| Build spans (PDF/texto doc) | `build_spans_from_pdf()` / `build_spans_from_text()` | paths / texto | `document_spans` → `filter_spans` |
| Merge | `merge_approved_and_filtered_document_spans()` | `approved_note_spans` + documentos filtrados | `filtered_spans` con ids globales |
| Apply drops | `apply_span_drops()` | `Span[]` + `drop_ids: str[]` | `Span[]` filtrados |
| Propagate dates | `propagate_cluster_date_hints()` | `SpanCluster[]` + `Span[]` | `SpanCluster[]` con `date_hints[]` |
| Adapter jobs | `build_adapter_jobs()` | `ClassifyClustersResult` + `section_id` set | `dict[section_id, list[cluster_id]]` |

### Modelo `Span` (payload LLM)

```json
{
  "id": "12",
  "doc": "epicrisis",
  "kind": "paragraph|line|table_row|heading|result_line|unknown",
  "text": "literal",
  "flags": []
}
```

`span_to_payload_item()` omite `flags` si está vacío. Los `id` son strings numéricas secuenciales (`"1"`, `"2"`, …) asignadas al construir/mergear el pool.

---

### 5. Triage

| | |
|---|---|
| **LLM** | Sí |
| **Input (dominio)** | `DoctorItem[]` (segmentos de la nota; `id` numérico `"1"`, `"2"`, …) |
| **User al modelo** | bloque `<input_json>` con `{session_id, manifest{available_documents, template_section_ids}, items[{id, text}]}` |
| **Output parseado** | `TriageResult` → `{directives[], content_ids[], drop_ids[]}` |
| **Salida downstream** | `approved_note_spans` (bypass filter) + `document_directive_filter` / adapter / generation vía `directives` por scope |

| Versión | System | User | Structured output |
|---------|--------|------|-------------------|
| **v001** (default) | `triage_prompt_v001.py` → `SYSTEM_PROMPT` | `<input_json>` con `session_id`, `manifest`, `items` | Sí |

**Output:**

```json
{
  "directives": [
    {
      "scope": "document",
      "action": "limit_source_to",
      "target": "case2_epicrisis",
      "topic": "neumonía"
    }
  ],
  "content_ids": [3],
  "drop_ids": [1, 2]
}
```

`Directive` usa `scope` (`document` | `transcript` | `generation`) + `action` + campos opcionales (`target`, `topic`, `section_id`, `instruction`). Prohibido `transcript.ignore_source`. `transcript.limit_to_topic` requiere `section_id`.

---

### 6. Filter spans

| | |
|---|---|
| **LLM** | Sí |
| **Input (dominio)** | `Span[]` de documentos + `encounter_date?` + `document_date?` (filtro clínico general; sin directives de triage) |
| **Output parseado** | `FilterSpansResult` → `{drop_ids: str[]}` |
| **Post-proceso** | `apply_span_drops()` solo sobre `document_spans` |
| **Salida downstream** | `document_directive_filter` → merge con `approved_note_spans` → `cluster_spans` |

| Versión | System | User | Structured output |
|---------|--------|------|-------------------|
| **v001** | `filter_spans_v001.txt` | JSON con `encounter_date`, `document_date`, `directives`, `spans` | No |
| **v002** (default) | `context_pipeline/filter_spans/prompts/filter_spans_prompt_v001.py` → `SYSTEM_PROMPT` | JSON con `encounter_date`, `document_date`, `directives`, `spans` (sin `date_hint`) | Sí (`drop_ids` con enum de span `id` conocidos) |

**Output:**

```json
{ "drop_ids": ["7"] }
```

---

### 6b. Document directive filter

| | |
|---|---|
| **LLM** | Solo para `limit_source_to` y `exclude_topic` (selector de span IDs) |
| **Input (dominio)** | `Span[]` ya filtrados clínicamente + `Directive[]` con `scope=document` |
| **Determinístico** | `ignore_source` elimina todos los spans del documento resuelto |
| **Selector** | devuelve `keep_ids[]` existentes; no reescribe texto |
| **Ambiguo** | target documental no resuelto → no aplicar destructivamente; auditar |
| **Preferencias** | `use_source` / `prefer_topic` no filtran aquí; van al adapter |
| **Salida downstream** | spans documentales reducidos → merge con `approved_note_spans` |

| Versión | System | User | Structured output |
|---------|--------|------|-------------------|
| **v001** (default) | `document_directive_filter/prompts/span_selector_prompt_v001.py` | `<input_json>` con `directive` + `spans` | Sí (`keep_ids`) |

---

### 7. Cluster spans

| | |
|---|---|
| **LLM** | Sí |
| **Input (dominio)** | `Span[]` filtrados (solo `id` + `text` al modelo; `date_hint` como atributo en v002) |
| **Output parseado** | `SpanCluster[]` → `{id, title, span_ids: str[]}` |
| **Post-proceso** | `propagate_cluster_date_hints()` |
| **Salida downstream** | clusters → classify_clusters |

| Versión | System | User | Structured output |
|---------|--------|------|-------------------|
| **v001** | `cluster_spans_v001.txt` | JSON `{ "spans": [{ "id", "text" }] }` | No |
| **v002** (default) | `context_pipeline/cluster_spans/prompts/cluster_spans_prompt_v001.py` → `SYSTEM_PROMPT` | Bloque `<spans>` con `<span id="...">` (opcional `date_hints="..."`) | Sí |

**Output v002:**

```json
{
  "clusters": [
    {
      "id": "c1",
      "title": "alergia_penicilina_urticaria",
      "span_ids": ["1", "2"]
    }
  ]
}
```

v002 exige `title` por cluster y cobertura completa de span ids (cada span exactamente una vez).

---

### 8. Classify clusters

| | |
|---|---|
| **LLM** | Sí |
| **Input (dominio)** | `SpanCluster[]` + `Span[]` + `ClinicalTemplate` + fechas |
| **User al modelo** | v001: JSON · v002: `<encounter_context>`, `<template_sections>`, `<clusters>`, `<source_spans>` |
| **Output parseado** | `ClassifyClustersResult` → `{assignments[{cluster_id, section_ids[]}]}` |
| **Post-proceso** | `build_adapter_jobs()`; `section_ids: []` = cluster descartado |
| **Salida downstream** | jobs por sección → section_adapter |

| Versión | System | User | Structured output |
|---------|--------|------|-------------------|
| **v001** | `classify_clusters_v001.txt` | `template_sections[]`, `clusters[]`, `spans[]` | No |
| **v002** (default) | `context_pipeline/classify_clusters/prompts/classify_clusters_prompt_v001.py` → `SYSTEM_PROMPT` | Bloques `<encounter_context>`, `<template_sections>`, `<clusters>`, `<source_spans>` | Sí |

**Output v002:**

```json
{
  "assignments": [
    { "cluster_id": "c1", "section_ids": ["antecedentes", "estudios_y_resultados"] },
    { "cluster_id": "c2", "section_ids": [] }
  ]
}
```

`section_ids: []` marca el cluster como descartado: no entra al `section_adapter`. v002 exige un assignment por cada cluster de entrada.

Alta sensibilidad: un cluster puede ir a varias secciones cuando el contenido es transversal.

---

### 9. Section adapter

| | |
|---|---|
| **LLM** | Sí (una llamada por sección con clusters asignados) |
| **Input (dominio)** | `section_id` + clusters del job + `Span[]` referenciados + plantilla + `Directive[]` |
| **Rol** | Preparar **contexto seccional** (`brief`), no redactar la sección final |
| **User al modelo** | v003: `<section>` + `<guidelines>` + `<input_json>` · v002/v001: JSON |
| **Output parseado** | `SectionAdapterResult` → `{section_id, brief}` (`content` legacy aceptado) |
| **Salida downstream** | `section_context: dict[str, str]` → generation v003 campo `context` |

| Versión | System | User | Structured output |
|---------|--------|------|-------------------|
| **v001** | `section_adapter_v001.txt` | JSON sin `section_guidelines` | No · output `{content}` |
| **v002** | `section_adapter_v002.txt` | JSON + `section_guidelines` | No · output `{content}` |
| **v003** (default) | `adapter_prompt_v001.py` → `SYSTEM_PROMPT` | `<section>`, `<guidelines>`, `<input_json>` (fechas, directivas, clusters, spans) | Sí (`brief`, `section_id` const) |

#### v003 — user payload

```
Ahora procesa el siguiente caso.

<section>
id: antecedentes
description: Antecedentes médicos...
</section>

<guidelines>
Incluye: ...
</guidelines>

<input_json>
{
  "encounter_date": "2026-06-14",
  "doc_date": "2024-03-01",
  "directives": [...],
  "clusters": [...],
  "spans": [...]
}
</input_json>
```

**Output v003:**

```json
{
  "section_id": "antecedentes",
  "brief": "Epicrisis previa: hospitalización por neumonía adquirida en la comunidad en marzo de 2024, con evolución favorable."
}
```

`brief: ""` → la sección no entra en `section_context`. Si el contexto solo advierte no usarlo como actual, devolver vacío.

**Export sesión:** `section_context: { "section_id": "brief", ... }` — solo briefs no vacíos.

#### Legacy v002 — user JSON

```json
{
  "section_id": "estudios_y_resultados",
  "section_description": "...",
  "section_guidelines": "Incluye:\n...\n\nLímites:\n...",
  "encounter_date": "2026-06-14",
  "directives": [...],
  "clusters": [{ "id", "span_ids", "title" }],
  "spans": [{ "id", "doc", "kind", "text" }]
}
```

**Output legacy:** `{ "section_id", "content" }` — el parser normaliza `content` → `brief`.

**Export adicional:** `section_evidence: dict[section_id, list[{id, doc, text, date_hint?}]]` — pool de spans por sección para auditoría en generation (sin LLM extra).

---

## Generation — dos rutas (v001 py-prompt)

| Ruta | Módulos | Cuándo | LLM calls |
|------|---------|--------|-----------|
| **Directo** (`section_generator_direct`) | `prompts/direct/generation_direct_prompt_v001.py` | Toggle **Linked evidence** OFF | 1 |
| **Two-step** (planner → renderer) | `prompts/two_step/section_planner_prompt_v001.py` → `prompts/two_step/section_renderer_prompt_v001.py` | Toggle **Linked evidence** ON (todas las secciones, v001) | 2 |

En el harness Streamlit, runs `two_step` exportan por sección `generation_route`, `planner_items`, `planned_items_block` y `llm_responses[]` con `step` (`planner` / `renderer`) incluso en `output_detail=compact`. La UI ofrece toggle **Mostrar IDs de evidencia** y expander **Auditoría linked evidence** en Generation, Run E2E e Historial.

- **Legacy v003** (`.txt` + JSON verboso) sigue disponible; opt-in por `prompt_version`.
- **Directo (v001):** metadatos en bloques XML; `<input_json>` con `conversation_groups` + `context_brief`.
- **Planner (two-step):** input en bloque `<evidence>`; output JSON mínimo `{"items":[{"text":"...","e":["t1","s2"]}]}` sin `section_id`.
- **Renderer (two-step):** recibe `<planned_items>` renderizado (lista numerada con `evidence: id,...`) + `<generation_mode>`; produce Markdown final con markers `{{e:...}}`.
- **Validación post-LLM:** planner valida IDs en `e[]`; renderer valida markers con `audit_evidence_markers`.
- **Record export:** `generation_route`, `planner_items`, `planned_items_block`, `content` (con markers), `llm_responses[]`. Runs viejos pueden traer `draft_with_evidence` (texto libre); la UI lo trata como legado.

---

## E2E — cómo se encadenan (`ui/runner.run_e2e_pipeline`)

`run_e2e_pipeline` devuelve `E2EPipelineResult` (`status`, `outputs`, `failed_step`, `error_message`, `manifest_path`).

- **`status: complete`**: los cuatro pasos transcript terminaron bien.
- **`status: failed`**: un paso falló; `outputs` conserva los pasos exitosos previos más un record sintético del paso fallido (`step_status: failed`). Los pasos posteriores no se ejecutan.

Persistencia (`ui/e2e_runs.save_e2e_run` / `load_e2e_run`): el manifest guarda `status`, `failed_step`, `error_message` y `outputs[]` parciales. En historial, runs fallidos se etiquetan p. ej. `failed at classification`.

Si falla `generation`, el error record incluye `section_id`, `generation_substep` (`direct` | `planner` | `renderer`), diagnóstico LLM y, en fallos de renderer, el output del planner. OpenAI: un retry automático ante `ai_pipeline_openai_empty_response` (`retry_count=1`).

**Prompts/schemas:** metadata centralizada en `common/pipeline_steps.py` y runtime en `common/prompt_runtime.py`. El context pipeline compuesto usa `ContextPipelinePromptBundle` con versiones por subpaso (`context_pipeline/config.py`).

**Anthropic structured output:** si el schema JSON incluye keywords no soportados (p. ej. `oneOf` en triage), el provider omite `output_config` y valida después con parse + Pydantic; `request_params` registra el fallback.

**Run E2E full:** plantilla fija `consulta_estructurada_v001` (`E2E_FULL_TEMPLATE_ID`). Contexto extra opcional vía nota/PDF → `run_context_ad_hoc_pipeline_step` (step `context_ad_hoc_pipeline`). El mini E2E de contexto independiente sigue permitiendo otros templates.

1. `filtering` → `drop_turn_ids`
2. Transcript filtrado → `clustering` → clusters con turns
3. Clusters + `template_id` → `classification` → `assignments`
4. *(Opcional)* `context_ad_hoc_pipeline` → JSON con `section_context` (nota y/o PDF custom)
5. `generation` por sección:
   - clusters asignados desde classification
   - `context` desde `load_section_context_from_record(claim_classification_result_file)`
   - `section_evidence` desde `load_section_evidence_from_record` (mismo JSON)

Parámetros típicos debug:

```bash
# Solo transcript
make -C classification debug-session SESSION_ID=case1 PROVIDER=openai \
  PROMPT_VERSION=v003 TEMPLATE_ID=consulta_estructurada_v001

# Context + adapter v002
# PROMPT_VERSION=v002 en section_adapter, TEMPLATE_ID=consulta_estructurada_v001
```

---

## Resumen: qué produce cada etapa

| Etapa | LLM | Input (dominio) | Output parseado | Texto clínico |
|-------|-----|-----------------|-----------------|---------------|
| turn catalog | No | `TranscriptCase` | `list[{turn_id, speaker, text}]` | No |
| filtering | Sí | turn catalog | `FilteringResult` (`drop_turn_ids: int[]`) | No |
| clustering | Sí | turn catalog filtrado | `ClusteringResult` (`clusters`, `unassigned_turn_ids?`) | No |
| clustering repair | Sí | clusters + missing turns | `{assignments, unassigned_turn_ids}` | No |
| classification | Sí | `ClusterCase[]` + plantilla | `{assignments[{cluster_id, section_ids}]}` | No |
| triage | Sí | `DoctorItem[]` | `TriageResult` | No |
| build / merge spans | No | nota, PDF, texto | `Span[]` | No |
| filter_spans | Sí | `Span[]` + fechas + directivas | `FilterSpansResult` (`drop_ids: str[]`) | No |
| cluster_spans | Sí | `Span[]` filtrados | `SpanCluster[]` | No |
| classify_clusters | Sí | clusters + spans + plantilla | `ClassifyClustersResult` | No |
| section_adapter | Sí | job por sección | `SectionAdapterResult` → `section_context` + `section_evidence` | Preparatorio (`brief`) |
| generation | Sí | sección + clusters + context + evidence | `content` con markers `{{e:...}}`; export `planner_items` + `planned_items_block` | **Sí** (nota final) |

---

## Archivos de referencia en código

| Concern | Módulo |
|---------|--------|
| Prompts `.py` / registro | `common/prompt_registry.py` |
| Bloques model-facing | `common/prompt_blocks.py` |
| Plantillas | `common/templates.py` |
| Transcript / turns | `common/transcripts.py` |
| Spans, triage, adapter models | `common/context_spans.py` |
| Payload classification | `classification/lib.py` |
| Payload generation | `generation/lib.py` |
| Context orchestration | `context_pipeline/session.py` |
| Puentes E2E | `ui/bridge.py`, `ui/runner.py` |
| Defaults UI | `ui/discovery.py` |

---

## Notas

- **TEMPLATE_ID por defecto en UI:** no es `consulta_estructurada_v001`; hay que pasarlo explícitamente en debug/E2E.
- **Classification default:** `v004` (módulo `.py`); `v003` sigue disponible como `.txt`.
- **Filtering / clustering default:** `v002` (módulo `.py`); `v001` sigue disponible como `.txt`.
- **Rollout Fase 2:** context steps, generation y section_adapter migrarán al mismo patrón en PRs independientes.
- **SSE / multi-instancia:** no aplica aquí; esto es harness local.
- **v002 plantilla:** `include`/`boundaries` en JSON; `classification.guidelines` / `generation.guidelines` por sección vacíos; la guía llega compuesta en runtime.
- **Próximo:** guidelines crudos por sección pueden volver a llenarse además de include/boundaries; `compose_section_guidelines` concatena ambos.
