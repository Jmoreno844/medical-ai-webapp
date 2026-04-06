# Cloud Functions Module

Este directorio contiene la lógica serverless que habla con Gemini.

## Responsabilidades

- `endpoints/transcription_endpoint.py`
  - valida requests de transcripción
  - invoca servicios de audio/transcripción
  - devuelve contenido a Django
- `endpoints/document_workflow.py`
  - valida requests de generación documental
  - soporta `validate_only`
  - transmite chunks a Django

## Regla de diseño

- Los endpoints validan y orquestan.
- La lógica reusable vive en `services/`.
- Los callbacks HTTP a Django viven en `services/django_api.py`.
- No agregues acceso directo a base de datos aquí.

## Contrato crítico

Si cambias un payload aquí, confirma el endpoint espejo en `backend/apps/documents/api/`.

## Observabilidad local

- OpenTelemetry sigue cubriendo spans HTTP y callbacks locales.
- LangSmith ahora puede activarse solo en `ENVIRONMENT=local` con `LANGSMITH_API_KEY` + `LANGSMITH_PROJECT=cloud-functions-local`.
- Los traces de LangSmith se limitan a metadata sanitizada: IDs, flags, tamaños y modelo. No envían transcripciones completas, documentos generados ni tokens.
