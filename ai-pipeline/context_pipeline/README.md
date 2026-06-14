# Context pipeline (spans + section_context)

External context from doctor notes and patient documents, merged into generation as `section_context`.

## Flow

```
doctor_note → split_doctor_items (code) → triage (LLM: directives + content_ids + drop_ids)
documents / pasted text → build_spans (code) → spans
[content_ids] → doctor_items_to_spans (code) → spans (doc=nota_medico)
spans pool → filter_spans → cluster_spans → classify_clusters → section_adapter → section_context
generation (per section) → transcript clusters + section_context[section_id]
```

Only `section_adapter` generates clinical text. Intermediate LLM steps return IDs/mappings only.

## Modules

| Folder | Role |
|--------|------|
| [`cases/`](cases/) | Context case fixtures (`encounter_date`, `document_date`) |
| [`spans/`](spans/) | PDF text extraction for `build_spans_from_pdf` |
| [`triage/`](triage/) | Separate directives from clinical items |
| [`filter_spans/`](filter_spans/) | Drop irrelevant spans (conservative) |
| [`cluster_spans/`](cluster_spans/) | Group related span IDs |
| [`classify_clusters/`](classify_clusters/) | Route clusters to template sections |
| [`section_adapter/`](section_adapter/) | Produce `section_context` text per section |
| [`session.py`](session.py) | End-to-end orchestration |

Shared models/helpers: [`../common/context_spans.py`](../common/context_spans.py).

## Debug

```bash
cd ai-pipeline
uv run pytest context_pipeline generation -q
```

Interactive harness: `uv run streamlit run ui/app.py` → **Contexto externo** branch.
