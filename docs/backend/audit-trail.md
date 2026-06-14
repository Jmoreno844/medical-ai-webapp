# Audit Trail Clínico

Este documento describe la auditoría clínica persistente del producto. Su
objetivo es dejar evidencia de acceso y acciones sobre recursos clínicos sin
mezclar ese fin con logs/traces operativos.

## Qué es y qué no es

- La auditoría clínica vive en PostgreSQL (`audit_user_session`,
  `audit_event`) y está pensada para evidencia operativa y revisiones internas.
- Los logs JSON y OpenTelemetry siguen siendo **metadata-only** para debugging y
  observabilidad. No sustituyen la auditoría clínica.
- La auditoría clínica **no** sustituye versionado del documento clínico, firma
  documental ni asesoría legal formal.

## Campos permitidos

Se guardan solo metadatos operativos y de correlación:

- `actor_id`, `actor_type`, `actor_role_snapshot`, `actor_name_snapshot`
- `session_id`
- `patient_id`, `encounter_id`, `document_id`
- `action`, `result`, `error_code`
- `service_name`, `service_account`
- `trace_id`, `request_id`
- timestamps

No se guardan en la auditoría:

- prompts
- transcripciones
- documentos generados
- cuerpos HTTP completos
- cookies, JWTs, callback tokens, signed URLs
- nombres de paciente, diagnósticos, emails o payloads libres

## Política de IP

- La identidad principal de la sesión es `actor_id + session_id + timestamp`.
- Cada sesión guarda `ip_hmac` y `network_prefix`.
- La IP completa se cifra en `ip_encrypted` solo para eventos de mayor valor de
  seguridad, como login, logout, recuperación de contraseña, accesos denegados,
  exportaciones y lectura interna del audit log.
- El HMAC permite correlación sin exponer la IP cruda; sigue siendo dato
  pseudonimizado, no anónimo.

Razón operativa y de compliance:

- minimiza dato personal repetido en eventos clínicos rutinarios
- conserva capacidad forense básica para eventos de seguridad
- evita usar la observabilidad como canal accidental de PHI

## Eventos v1

- `auth.login_success`
- `auth.login_failure`
- `auth.logout`
- `auth.password_recovery_requested`
- `clinical.encounter_opened`
- `clinical.document_opened`
- `clinical.access_denied`
- `document.created`
- `document.ai_regeneration_started`
- `document.ai_regeneration_completed`
- `document.edited`
- `document.deleted`
- `document.copied`
- `audio.upload_url_created`
- `audio.transcription_started`
- `audio.section_registered`
- `audio.transcription_completed`
- `audio.transcription_failed`
- `audio.deleted`
- `service.document_processed`
- `service.audio_processed`
- `audit.audit_log_viewed`
- `user.created`

Al borrar un documento, la fila clínica desaparece pero los eventos previos
permanecen. `audit_event.document_id` usa `ON DELETE SET NULL`; el ID
histórico queda en `resource_id` cuando el evento lo registró. El delete
explícito emite `document.deleted` **antes** del borrado físico.

El borrado de encuentro completo aún no emite eventos equivalentes; ver
[`../debt/encounter-delete-audit-trail.md`](../debt/encounter-delete-audit-trail.md).

Algunos eventos del plan original siguen pendientes de que exista el flujo de
producto correspondiente, por ejemplo `document.exported` o
`support.customer_data_accessed`. Eventos de cuenta ya emitidos:
`user.activated`, `user.deactivated`, `clinical_access.enabled`,
`clinical_access.disabled`.

## Acceso y retención

- La lectura se hace por `GET /api/v1/internal/audit-events`.
- La SPA expone una zona interna `/admin` con vistas `Audit Trail` y `Usuarios`
  para roles administrativos, sobre estos endpoints internos.
- El acceso requiere `is_staff`, `is_superuser` o rol administrativo explícito.
- `GET /api/v1/auth/me` expone capacidades derivadas del backend:
  `can_access_admin_panel`, `can_view_audit`, `can_manage_users`.
- Cada consulta a ese endpoint genera `audit.audit_log_viewed`.
- En v1 no hay borrado automático; legal/compliance debe definir la política de
  retención formal antes de producción con datos reales.

## Fronteras de visibilidad del panel interno

Se permite mostrar:

- nombre, apellido, email y rol del usuario/médico
- estado activo/inactivo y timestamps operativos
- `session_id`, `trace_id`, `request_id`, `service_name`, `error_code`
- IDs clínicos (`patient_id`, `encounter_id`, `document_id`) sin resolver
  nombres de paciente

No se muestra en esta fase:

- nombres de paciente
- diagnósticos, transcripciones o documentos
- prompts o payloads de IA
- IP completa desencriptada
- cookies, JWTs, callback tokens o signed URLs

La vista `Usuarios` puede mostrar `ip_hmac` y `network_prefix` para soporte
operativo básico, pero nunca la IP cruda.

## Nota legal

Este diseño intenta ser safe-by-default para software médico:

- separa observabilidad de auditoría
- reduce exposición de dato personal y clínico
- facilita controles IAM y revisiones posteriores

No reemplaza validación legal local sobre retención, derechos de acceso,
políticas de soporte ni requisitos regulatorios específicos del país.
