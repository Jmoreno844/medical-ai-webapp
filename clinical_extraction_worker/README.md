# Clinical Extraction Worker

Worker Cloud Run privado para extracción clínica shadow (`ClinicalFactsV1`).

## Flujo

1. FastAPI consolida una sesión de transcripción segmentada.
2. Si `CLINICAL_EXTRACTION_ENABLED=true`, encola o invoca localmente este worker
   con `session_id`.
3. El worker pide a FastAPI el work item interno con `transcript_json.chunks[]`.
4. Llama al provider configurado y devuelve el resultado con callback JWT.
5. FastAPI persiste salida cruda, facts post-grounding, evidencia y métricas.

No modifica `documents_document.content_markdown`, generación documental, plantillas
ni SSE.

## Variables

- `ENVIRONMENT=local`
- `BACKEND_INTERNAL_BASE_URL=http://localhost:8001`
- `CLINICAL_EXTRACTION_PROVIDER=gemini`
- `CLINICAL_EXTRACTION_MODEL=gemini-2.5-flash`
- `CLINICAL_EXTRACTION_OPENAI_MODEL=gpt-5.4-mini`
- `GCP_PROJECT_ID` y `VERTEX_AI_LOCATION=global` para Gemini en Vertex AI
- `OPENAI_API_KEY` si `CLINICAL_EXTRACTION_PROVIDER=openai`
- `CLOUD_TASKS_INVOKER_SERVICE_ACCOUNT` en Cloud Run privado

## Local

```bash
uv sync --group dev
ENVIRONMENT=local \
BACKEND_INTERNAL_BASE_URL=http://localhost:8001 \
GCP_PROJECT_ID=tu-proyecto \
uv run uvicorn app.main:app --host 0.0.0.0 --port 8093 --reload
```

En el backend local configura:

```bash
CLINICAL_EXTRACTION_ENABLED=true
CLINICAL_EXTRACTION_WORKER_BASE_URL=http://localhost:8093
```

## Tests

```bash
python -m pytest clinical_extraction_worker/tests
```
