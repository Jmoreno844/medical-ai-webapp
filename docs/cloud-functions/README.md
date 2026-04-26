# Cloud Functions

El directorio `cloud_functions/` contiene la generación documental serverless con Gemini. La transcripción nueva corre en FastAPI mediante Cloud Tasks y Google Gen AI SDK async; la función de transcripción queda como legacy.

## Qué vive aquí

- `functions/endpoints/document_workflow.py` — entrypoint HTTP para generación de documentos.
- `functions/endpoints/transcription_endpoint.py` — legacy para transcripción.
- `functions/services/transcription/` — legacy para procesamiento de audio desde `gs://`.
- `functions/services/document_generation/` — prompt building, streaming y formateo.
- `functions/services/backend_api.py` — callbacks HTTP hacia el backend versionado (`PATCH` de contenido, chunks de generación, notify complete).
- `functions/tracing.py` — OpenTelemetry (span por request + propagación en `requests` hacia el backend). Variables: [`../backend/tracing.md`](../backend/tracing.md).
- `functions/langsmith_tracing.py` — LangSmith local-first para request/model spans con metadata sanitizada.

## Modelo de despliegue en `stg`

- Terraform crea el bucket fuente `gs://<project>-cf-source`, las service accounts y los permisos necesarios.
- El runtime de las funciones **no** lo crea Terraform en `stg`.
- El workflow [`deploy-cloud-function-stg.yaml`](../../.github/workflows/deploy-cloud-function-stg.yaml) empaqueta el código, sube el zip al bucket fuente y despliega `document-workflow` con `gcloud functions deploy`.
- El mismo workflow aplica el binding IAM de invocación para `backend-runner`.

## Variables de entorno clave

| Variable                         | Uso                                                                 |
| -------------------------------- | ------------------------------------------------------------------- |
| `BACKEND_API_BASE_URL`           | URL base del backend para callbacks versionados.                     |
| `BACKEND_API_VERSION`            | Versión del API backend para callbacks; default local: `v1`.         |
| `GCP_PROJECT`                    | Proyecto usado para inicializar Vertex AI.                          |
| `GCP_REGION`                     | Región de Vertex AI.                                                |
| `GEMINI_MODEL`                   | Modelo de Gemini a usar.                                            |
| `GOOGLE_APPLICATION_CREDENTIALS` | Ruta **dentro del contenedor** al JSON de credenciales (ver abajo). |
| `LANGSMITH_TRACING`              | Activa tracing local en LangSmith si también hay API key + project. |
| `LANGSMITH_API_KEY`              | API key de LangSmith para el runtime local.                         |
| `LANGSMITH_PROJECT`              | Proyecto LangSmith recomendado: `cloud-functions-local`.            |

En local con Docker Compose, `GEMINI_MODEL` se toma de `functions/.env.local`. En despliegue por GitHub Actions, el workflow lee la variable `GEMINI_MODEL` desde el environment de GitHub `stg` si existe; si no, usa `gemini-3.1-flash-lite-preview`.

El tracing a LangSmith en este servicio es solo para `ENVIRONMENT=local` y registra metadatos de request/modelo, no el texto completo de transcripciones, prompts ni documentos generados.

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

## Contrato con el backend

- El backend encola la transcripción en Cloud Tasks hacia un endpoint interno de FastAPI y llama la generación de documentos por HTTP directo.
- Las funciones devuelven resultados al backend usando `Authorization: Bearer <jwt>`.
- Los chunks de generación se envían de vuelta al backend y luego salen al navegador por SSE.
- Durante la migración actual, los callbacks clínicos apuntan a FastAPI bajo `/api/v1`.

## Logging

- No loguear chunks completos ni respuestas completas del modelo.
- Loguear `document_id`, `process_id`, tamaños y flags de estado.

## Cómo se conecta con el resto

- El flujo global está en [`../architecture/system-overview.md`](../architecture/system-overview.md).
- La decisión arquitectónica relevante está en [`../decisions/0003-procesamiento-asincrono-de-audio.md`](../decisions/0003-procesamiento-asincrono-de-audio.md).
