# Logging en backend

## Configuración

- Configuración central del backend en `backend_fastapi/app/core/`.
- Nivel efectivo controlado por variables de entorno del servicio (`DEBUG`, `OTEL_*`, `GOOGLE_CLOUD_PROJECT` según aplique).
- El filtro `TraceContextFilter` añade `trace_id` y `span_id` del span OTel activo a cada registro (formato de consola: `trace_id=… span_id=…`). En GCP, si existe `GOOGLE_CLOUD_PROJECT` / `GCP_PROJECT`, también se calcula `google_cloud_trace` para correlación con Cloud Logging / Cloud Trace (ver [tracing.md](tracing.md)).

## Comportamiento por entorno

- `ENVIRONMENT=local` favorece logs de desarrollo.
- `ENVIRONMENT=stg` / `prod` deben conservar correlación con Cloud Trace cuando OTel está habilitado.
- `ENVIRONMENT=test` evita configuración pesada de observabilidad.

## Reglas de contenido

- Nunca usar `print()` en código de aplicación.
- Usar `logging.getLogger(__name__)`.
- No loguear texto clínico completo, payloads enteros, tokens, session keys ni credenciales.
- Si hace falta trazar una operación sensible, loguear metadatos y no contenido.

## Relación con otros servicios

- El frontend usa su propia política en [`../frontend/logging.md`](../frontend/logging.md).
- Cloud Functions, `transcription_worker` y `document_generation_worker` deben
  seguir el mismo principio de saneamiento: metadatos sí, contenido clínico no.
- `transcription_worker` puede loguear `section_id`, `session_id`,
  `document_id`, `encounter_id`, decisión VAD, latencias, modelo y códigos de
  error. No debe loguear transcripciones, audio, signed URLs, prompts,
  respuestas crudas de Gemini, JWTs/OIDC ni payloads completos.
- `document_generation_worker` puede loguear `process_id`, `document_id`,
  `encounter_id`, `doctor_template_id`, modelo, latencias y códigos de error.
  No debe loguear prompts, documentos, transcripciones, chunks generados,
  respuestas crudas de Gemini, JWTs/OIDC ni payloads completos.
