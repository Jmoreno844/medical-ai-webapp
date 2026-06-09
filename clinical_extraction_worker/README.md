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
- `CLINICAL_EXTRACTION_ANTHROPIC_MODEL=claude-haiku-4-5-20251001`
- `GCP_PROJECT_ID` y `VERTEX_AI_LOCATION=global` para Gemini en Vertex AI
- `OPENAI_API_KEY` si `CLINICAL_EXTRACTION_PROVIDER=openai`
- `ANTHROPIC_API_KEY` si `CLINICAL_EXTRACTION_PROVIDER=anthropic_api`
- `CLOUD_TASKS_INVOKER_SERVICE_ACCOUNT` en Cloud Run privado

## Local

```bash
cp .env.local.example .env.local
# edit GCP_PROJECT_ID (and OPENAI_API_KEY if using openai)
uv sync --group dev
uv run uvicorn app.main:app --host 0.0.0.0 --port 8093 --reload
```

El worker carga variables desde `.env.local` (mismo patrón que
`transcription_worker` y `document_generation_worker`).

En el backend local configura:

```bash
CLINICAL_EXTRACTION_ENABLED=true
CLINICAL_EXTRACTION_WORKER_BASE_URL=http://localhost:8093
```

## Debug local

En `ENVIRONMENT=local` expone:

```http
POST /api/v1/dev/clinical-extraction/extract
```

Recibe un work item mínimo (`session_id`, `language`, `chunks[]`) y devuelve
`facts` sin pasar por FastAPI ni persistir en DB. Lo usa el bridge de FastAPI
para la página `/debug/extraccion`.

## Tests

```bash
python -m pytest clinical_extraction_worker/tests
```
