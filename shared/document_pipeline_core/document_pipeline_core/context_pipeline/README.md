# Context pipeline (spans + section_context)

External context from doctor notes and patient documents, merged into generation as `section_context`.

## Flow

```
doctor_note → split_doctor_items (code) → triage (LLM: directives + content_ids + drop_ids)
triage.content_ids → doctor_items_to_spans (code) → approved_note_spans (bypass filter_spans)
documents / pasted text → build_spans (code) → document_spans → filter_spans (LLM, clínico general)
filtered document_spans → document_directive_filter (ignore determinístico + selector LLM)
approved_note_spans + directive-filtered document_spans → merge → cluster_spans → classify_clusters → section_adapter → section_context
generation (per section) → transcript clusters + section_context[section_id] + transcript_constraints
```

Directives por scope:

| Scope | Dónde se aplica |
|-------|-----------------|
| `document.ignore_source` / `limit_source_to` / `exclude_topic` | `document_directive_filter` (antes de clustering) |
| `document.use_source` / `prefer_topic` | `section_adapter` (preferencias, no filtro destructivo) |
| `transcript.*` | generación por sección (planner en two-step; direct generator en ruta directa) |
| `generation.apply_instruction` | reservado para instrucciones de redacción en generación |

Solo `generation` produce prosa clínica final. El adapter prepara `brief` compacto por sección. Los pasos intermedios devuelven IDs/mappings.

## Modules

| Folder | Role |
|--------|------|
| [`cases/`](cases/) | Context case fixtures (`encounter_date`, `document_date`) |
| [`spans/`](spans/) | PDF text extraction for `build_spans_from_pdf` |
| [`triage/`](triage/) | Separate directives from clinical items |
| [`filter_spans/`](filter_spans/) | Drop irrelevant spans (conservative clinical filter) |
| [`document_directive_filter/`](document_directive_filter/) | Apply explicit document directives (`ignore`, `limit`, `exclude`) |
| [`cluster_spans/`](cluster_spans/) | Group related span IDs |
| [`classify_clusters/`](classify_clusters/) | Route clusters to template sections |
| [`section_adapter/`](section_adapter/) | Produce `section_context` briefs per section |
| [`session.py`](session.py) | End-to-end orchestration |

Shared models/helpers: [`../common/context_spans.py`](../common/context_spans.py).

## Debug

```bash
cd ai-pipeline
uv run pytest context_pipeline generation -q
```

Interactive harness: `uv run streamlit run ui/app.py` → **Contexto externo** branch.
