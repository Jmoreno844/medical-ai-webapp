# Deuda Técnica — Audit Trail en borrado de encuentro

## Estado

Aceptada y explícita.

## Contexto

El borrado explícito de un documento (`DELETE /documents/{id}`) ya registra
`document.deleted` y conserva el historial de auditoría previo gracias a
`audit_event.document_id ON DELETE SET NULL`.

El borrado de un encuentro completo (`DELETE /encounters/{id}`) sigue eliminando
documentos, audio y filas copilot en cascada **sin** emitir eventos de
auditoría equivalentes.

## Impacto actual

- No queda evidencia de quién borró el encuentro ni cuándo.
- Los documentos eliminados en cascada no generan `document.deleted` por cada uno.
- Los eventos previos que apuntaban al encuentro o sus documentos conservan
  metadatos, pero el delete masivo no deja un evento terminal claro.

## Por qué se aceptó temporalmente

- El fix prioritario era desbloquear el delete de documento individual con
  historial intacto.
- El delete de encuentro es menos frecuente en producto y requiere decidir si
  el evento es uno solo (`encounter.deleted`) o uno por documento borrado en
  cascada.
- También falta alinear FKs similares (`audit_event.encounter_id`) si el
  encuentro desaparece físicamente.

## Owner

- `backend_fastapi/app/domains/encounters/`
- `backend_fastapi/app/domains/audit/`
- `docs/backend/audit-trail.md`

## Trigger para pagarla

- Antes de exponer delete de encuentro en producción con datos reales, o
- cuando compliance/soporte pida trazabilidad completa de borrados masivos.

## Trabajo pendiente sugerido

1. Definir evento(s): `encounter.deleted` y/o `document.deleted` en cascada.
2. Registrar el/los evento(s) **antes** del delete físico.
3. Evaluar `audit_event.encounter_id ON DELETE SET NULL` (y revisar
   `patient_id` si aplica).
4. Añadir tests de integración para delete de encuentro con filas en
   `audit_event`.

## Referencias

- [`docs/backend/audit-trail.md`](../backend/audit-trail.md)
- [`backend_fastapi/app/domains/encounters/api.py`](../../backend_fastapi/app/domains/encounters/api.py)
- Migración `0013_audit_event_document_id_set_null.py`
