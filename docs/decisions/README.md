# Architecture Decision Records

Este directorio guarda los Architecture Decision Records (ADR) del sistema.

## Proposito

Los ADR documentan decisiones arquitectonicas importantes, su contexto, las alternativas consideradas y sus consecuencias. Aqui deben vivir decisiones que afecten a mas de un servicio, por ejemplo `backend_fastapi/`, `cloud_functions/`, `webapp/` o el despliegue en Google Cloud.

## Convenciones

- Un archivo por decision.
- Prefijo numerico incremental: `0001-...`, `0002-...`.
- Nombre corto y descriptivo en kebab-case.
- Estatus sugeridos: `Proposed`, `Accepted`, `Superseded`, `Deprecated`.

## Estructura sugerida

Cada ADR deberia incluir al menos estas secciones:

- Titulo
- Estatus
- Contexto
- Alternativas consideradas
- Decision
- Consecuencias

## Indice

- [0002. Notificaciones en tiempo real (SSE en memoria)](0002-notificaciones-en-tiempo-real-sse-en-memoria.md)
- [0003. Procesamiento asincrono de audio](0003-procesamiento-asincrono-de-audio.md)
- [0004. Procesamiento asincrono de agentes de IA](0004-procesamiento-asincrono-agentes-ia.md)
- [0005. Aislamiento de cargas de trabajo IA (LangGraph)](0005-aislamiento-cargas-trabajo-ia-langgraph.md)
- [0006. Diferir explicit context caching para un futuro QA helper clínico](0006-explicit-context-caching-futuro-qa-helper.md)
- [0007. Anchors por contenido y lectura completa explícita en el writer flow](0007-writer-flow-anchors-y-lectura-completa.md)
- [0008. Transcripcion segmentada near realtime con GCS, Cloud Tasks y Gemini](0008-transcripcion-segmentada-near-realtime.md)
