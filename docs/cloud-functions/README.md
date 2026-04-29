# Cloud Functions

El directorio `cloud_functions/` conserva solo transcripción legacy. La
transcripción nueva corre en `transcription_worker/` y la generación documental
corre en `document_generation_worker/`.

## Qué vive aquí

- `functions/endpoints/transcription_endpoint.py` — legacy para transcripción.
- `functions/services/transcription/` — legacy para procesamiento de audio desde `gs://`.
- `functions/services/backend_api.py` — callbacks HTTP legacy hacia el backend versionado.
- `functions/tracing.py` — OpenTelemetry (span por request + propagación en `requests` hacia el backend). Variables: [`../backend/tracing.md`](../backend/tracing.md).
- `functions/langsmith_tracing.py` — LangSmith local-first para request/model spans con metadata sanitizada.

## Modelo de despliegue en `stg`

- Terraform crea el bucket fuente `gs://<project>-cf-source`, las service accounts y los permisos necesarios.
- El runtime de las funciones **no** lo crea Terraform en `stg`.
- El workflow [`deploy-cloud-function-stg.yaml`](../../.github/workflows/deploy-cloud-function-stg.yaml) empaqueta el código, sube el zip al bucket fuente y despliega `transcription-endpoint` con `gcloud functions deploy`.
- El mismo workflow aplica el binding IAM de invocación para `backend-runner`.

## Variables de entorno clave

| Variable                         | Uso                                                                 |
| -------------------------------- | ------------------------------------------------------------------- |
| `BACKEND_API_BASE_URL`           | URL base del backend para callbacks versionados.                     |
| `BACKEND_API_VERSION`            | Versión del API backend para callbacks; default local: `v1`.         |
| `GCP_PROJECT`                    | Proyecto usado para inicializar Vertex AI.                          |
| `GCP_REGION`                     | Región de Vertex AI.                                                |
| `GEMINI_MODEL`                   | Modelo de Gemini para transcripción legacy.                         |
| `GOOGLE_APPLICATION_CREDENTIALS` | Ruta **dentro del contenedor** al JSON de credenciales (ver abajo). |
| `LANGSMITH_TRACING`              | Activa tracing local en LangSmith si también hay API key + project. |
| `LANGSMITH_API_KEY`              | API key de LangSmith para el runtime local.                         |
| `LANGSMITH_PROJECT`              | Proyecto LangSmith recomendado: `cloud-functions-local`.            |

En local con Docker Compose, `GEMINI_MODEL` se toma de `functions/.env.local`.

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

- El backend encola transcripción por secciones hacia `transcription_worker` y
  generación documental hacia `document_generation_worker`. Esta Cloud Function
  queda solo para el flujo legacy de audio completo.
- Las funciones devuelven resultados al backend usando `Authorization: Bearer <jwt>`.
- Durante la migración actual, los callbacks clínicos apuntan a FastAPI bajo `/api/v1`.

## Logging

- No loguear chunks completos ni respuestas completas del modelo.
- Loguear `document_id`, `process_id`, tamaños y flags de estado.

## Cómo se conecta con el resto

- El flujo global está en [`../architecture/system-overview.md`](../architecture/system-overview.md).
- La decisión arquitectónica relevante está en [`../decisions/0003-procesamiento-asincrono-de-audio.md`](../decisions/0003-procesamiento-asincrono-de-audio.md).
