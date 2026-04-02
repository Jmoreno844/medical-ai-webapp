# Documents App

`apps/documents/` es la parte más sensible del backend porque conecta editor, SSE, generación documental y callbacks desde Cloud Functions.

## Qué es dueño de este módulo

- CRUD de `Document`
- Kickoff de generación documental autenticada por sesión
- Recepción de callbacks Bearer JWT desde Cloud Functions
- Emisión de eventos SSE al frontend

## Qué no es dueño de este módulo

- Inicio de transcripción y Cloud Tasks: `apps/generative_ai/`
- Plantillas: `apps/templates/`
- Signed URLs / almacenamiento de audio: `apps/encounters/services/storage.py`

## Mapa rápido

- `api/base.py` — CRUD base de documentos
- `api/generation.py` — inicia generación documental
- `api/callbacks.py` — chunks, transcripción completa y callbacks protegidos con JWT
- `api/sse.py` — token SSE y streams
- `services/generation_runner.py` — arranque en background de la Cloud Function
- `services/sse_hub.py` — registro en memoria de suscriptores SSE

## Restricciones importantes

- `process_id` y `document_id` forman parte del contrato de seguridad de generación.
- El SSE hub es en memoria; no asumas difusión entre múltiples instancias.
- Si cambias payloads o nombres de endpoints, debes actualizar:
  - Django
  - Cloud Functions
  - frontend que consume SSE
  - documentación de auth/JWT

## Antes de editar

Lee `docs/backend/auth-and-jwt.md` si el cambio toca tokens, callbacks o SSE.
