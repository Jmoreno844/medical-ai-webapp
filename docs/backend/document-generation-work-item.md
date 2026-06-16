# Document generation — internal work item (backend → worker)

Public API `POST /api/v1/documents/generate` is unchanged in phase 1. The **internal** work item fetched by `document_pipeline_worker` now carries structured context.

## `context_inputs`

| Field | Phase 1 | Phase 2 |
|-------|---------|---------|
| `doctor_note_markdown` | Content of the doctor's context document (`content_markdown`) | Same |
| `external_documents` | Always `[]` | Uploaded PDFs / external clinical documents |

`context_content` remains on the payload as a legacy mirror of `doctor_note_markdown` for backward compatibility during rollout.

## Example (phase 1)

```json
{
  "context_inputs": {
    "doctor_note_markdown": "Antecedente relevante…",
    "external_documents": []
  },
  "context_content": "Antecedente relevante…"
}
```

## Worker behavior

- Transcript branch: shared core defaults (`filtering v002`, `clustering v002` + repair, `classification v004`).
- Context branch: context pipeline v2 (`triage → filter_spans → … → section_adapter`) when `doctor_note_markdown` is meaningful.
- Generation: `PIPELINE_GENERATION_ROUTE` (`direct` default; `two_step` supported).
- SSE progress steps remain coarse-grained: `filtering`, `clustering`, `classification`, `context`, `generation`.

## Code references

- Schema: `backend_fastapi/app/domains/documents/schemas.py` (`ContextInputsOut`)
- Construction: `backend_fastapi/app/domains/documents/generation_api.py`
- Parsing: `document_pipeline_worker/app/pipeline/orchestrator.py` (`parse_context_inputs`)
