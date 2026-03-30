# Architecture Decision Records

Este directorio guarda los Architecture Decision Records (ADR) del sistema.

## Proposito

Los ADR documentan decisiones arquitectonicas importantes, su contexto, las alternativas consideradas y sus consecuencias. Aqui deben vivir decisiones que afecten a mas de un servicio, por ejemplo `backend/`, `cloud_functions/`, `webapp/` o el despliegue en Google Cloud.

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

- [0001. Uso de Cloud Tasks para procesamiento de audio](0001-uso-de-cloud-tasks-para-procesamiento-de-audio.md)
