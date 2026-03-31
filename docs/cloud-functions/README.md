# Cloud Functions

El directorio `cloud_functions/` contiene las funciones serverless que hacen el trabajo pesado con Gemini: transcripción de audio y generación de documentos clínicos.

## Qué vive aquí

- `functions/endpoints/transcription_endpoint.py` — entrypoint HTTP para transcripción.
- `functions/endpoints/document_workflow.py` — entrypoint HTTP para generación de documentos.
- `functions/services/transcription/` — procesamiento de audio desde `gs://`.
- `functions/services/document_generation/` — prompt building, streaming y formateo.
- `functions/services/django_api.py` — callbacks hacia Django (`PATCH` de contenido, chunks de generación, notify complete).
- `functions/tracing.py` — OpenTelemetry (span por request + propagación en `requests` hacia Django). Variables: [`../backend/tracing.md`](../backend/tracing.md).

## Variables de entorno clave

| Variable | Uso |
|----------|-----|
| `DJANGO_API_BASE_URL` | URL base del backend Django para callbacks. |
| `GCP_PROJECT` | Proyecto usado para inicializar Vertex AI. |
| `GCP_REGION` | Región de Vertex AI. |
| `GEMINI_MODEL` | Modelo de Gemini a usar. |

## Contrato con Django

- Django invoca las funciones con payload JSON y JWT de vida corta.
- Las funciones devuelven resultados a Django usando `Authorization: Bearer <jwt>`.
- Los chunks de generación se envían de vuelta a Django y luego salen al navegador por SSE.

## Logging

- No loguear chunks completos ni respuestas completas del modelo.
- Loguear `document_id`, `process_id`, tamaños y flags de estado.

## Cómo se conecta con el resto

- El flujo global está en [`../architecture/system-overview.md`](../architecture/system-overview.md).
- La decisión arquitectónica relevante está en [`../decisions/0001-uso-de-cloud-tasks-para-procesamiento-de-audio.md`](../decisions/0001-uso-de-cloud-tasks-para-procesamiento-de-audio.md).
