# Contexts

Este directorio contiene la fuente de verdad actual del detalle de `Encuentro`.

## Orden de providers

`AppProviders.tsx` compone:

1. `EncuentroProvider`
2. `DocumentProvider`
3. `ContentProvider`
4. `TranscriptionProvider`
5. `GenerationProvider`

Ese orden importa porque los providers se consumen entre sí.

## Qué es dueño de cada contexto

- `EncuentroContext`
  - datos generales del encuentro y paciente
- `DocumentContext`
  - lista y selección de documentos
- `ContentContext`
  - contenido del documento activo y sincronización con el editor
- `TranscriptionContext`
  - flujo de transcripción, SSE y flags como `hasBeenTranscribed`
- `GenerationContext`
  - plantillas, kickoff de generación, SSE de chunks y estado del proceso

## Restricciones importantes

- Mantén la lógica de `EventSource` dentro de `TranscriptionContext` y `GenerationContext`.
- Evita duplicar el mismo estado en componentes hijos si ya existe en un contexto.
- `features/` debe componer UI sobre estos providers, no volver a crear managers paralelos del mismo flujo.
- Si una lógica reusable nace desde un feature, extráela como helper sin ownership global o muévela al context dueño.
