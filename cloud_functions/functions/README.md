# Cloud Functions Module

Este directorio contiene la lógica serverless que habla con Gemini.

## Responsabilidades

- `endpoints/transcription_endpoint.py`
  - valida requests de transcripción
  - invoca servicios de audio/transcripción
  - devuelve contenido al backend transaccional
- `endpoints/document_workflow.py`
  - valida requests de generación documental
  - soporta `validate_only`
  - transmite chunks al backend transaccional

## Regla de diseño

- Los endpoints validan y orquestan.
- La lógica reusable vive en `services/`.
- Los callbacks HTTP al backend viven en `services/django_api.py` (nombre legacy).
- El cliente de callbacks construye URLs versionadas como `/api/{BACKEND_API_VERSION}`.
  Por defecto usa `BACKEND_API_VERSION=v1` y `BACKEND_API_BASE_URL`; `DJANGO_API_BASE_URL`
  sigue aceptado como fallback temporal durante la migración.
- No agregues acceso directo a base de datos aquí.

## Contrato crítico

Si cambias un payload aquí, confirma el endpoint espejo versionado en `backend_fastapi/app/domains/`.

## Observabilidad local

- OpenTelemetry sigue cubriendo spans HTTP y callbacks locales.
- LangSmith ahora puede activarse solo en `ENVIRONMENT=local` con `LANGSMITH_API_KEY` + `LANGSMITH_PROJECT=cloud-functions-local`.
- Los traces de LangSmith se limitan a metadata sanitizada: IDs, flags, tamaños y modelo. No envían transcripciones completas, documentos generados ni tokens.
