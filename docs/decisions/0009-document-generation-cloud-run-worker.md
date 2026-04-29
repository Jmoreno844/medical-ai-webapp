# ADR-009: Generación documental en Cloud Run worker

## Estado

Aceptada.

## Contexto

La generación documental vivía en la Cloud Function `document-workflow`. Ese
camino funcionaba, pero mezclaba el runtime legacy de Cloud Functions con el
flujo clínico nuevo basado en FastAPI, Cloud Tasks y workers privados.

## Decisión

Mover la generación documental a `document_generation_worker/`, un servicio
Cloud Run privado. FastAPI conserva permisos, DB, callbacks, SSE y estado
canónico. El worker recibe Cloud Tasks con IDs, pide el work-item clínico a
FastAPI mediante OIDC, llama Gemini streaming y envía chunks al callback
existente `/api/v1/documents/generation-chunk`.

La task no debe contener prompts, transcripciones, documentos, callback tokens
ni payloads clínicos completos.

## Consecuencias

- Generación documental escala separada del backend y del worker de audio.
- FastAPI sigue siendo la única autoridad transaccional.
- La observabilidad del worker debe ser metadata-only; LangSmith se permite en
  local/stg solo con processors saneados y queda deshabilitado en prod.
- `cloud_functions/` queda solo para transcripción legacy mientras exista ese
  fallback.
