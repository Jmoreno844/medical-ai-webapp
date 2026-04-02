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
