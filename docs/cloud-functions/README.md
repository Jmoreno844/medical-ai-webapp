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
| `GOOGLE_APPLICATION_CREDENTIALS` | Ruta **dentro del contenedor** al JSON de credenciales (ver abajo). |

## Local con Docker: credenciales GCP (Vertex / Secret Manager / GCS)

El contenedor **no** usa automáticamente el ADC del host. Tras `gcloud auth application-default login` en tu máquina, el archivo de ADC suele estar en:

- Linux/macOS: `~/.config/gcloud/application_default_credentials.json`

**Recomendado (sin service account keys):** monta ese archivo en el contenedor y apunta `GOOGLE_APPLICATION_CREDENTIALS` a esa ruta interna.

En `cloud_functions/docker-compose.yml`, por servicio:

```yaml
environment:
  - GOOGLE_APPLICATION_CREDENTIALS=/app/adc.json
volumes:
  - ${HOME}/.config/gcloud/application_default_credentials.json:/app/adc.json:ro
```

Ajusta `functions/.env.local` para **no** sobrescribir `GOOGLE_APPLICATION_CREDENTIALS` a otra ruta, o comenta esa línea si usas el montaje anterior.

**Alternativa:** montar un JSON de service account en `./credentials/` (solo si tu organización permite crear keys). El compose ya monta `cloud_functions/credentials` en `/app/credentials`.

Tu usuario de GCP debe tener permisos suficientes en el proyecto (p. ej. Vertex AI User, acceso a secrets que la función lea, etc.).

Si el archivo de ADC no existe aún, ejecuta en el host: `gcloud auth application-default login`. Si `docker compose up` falla al montar `/app/adc.json`, comprueba que exista `~/.config/gcloud/application_default_credentials.json`.

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
