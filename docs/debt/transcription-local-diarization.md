# Deuda: diarizacion local ligera para transcripcion segmentada

## Estado

Aceptada temporalmente.

## Situacion actual

La diarizacion de la transcripcion segmentada depende principalmente de Gemini
por seccion. El frontend decide cortes y recortes de audio, pero no mantiene
identidad local consistente de hablantes entre fragmentos ni detecta overlaps
con una capa independiente.

## Mejora futura

Mas adelante se puede añadir una capa local ligera de diarizacion:

- embeddings de voz
- identidad consistente entre fragmentos
- deteccion local de overlap
- reconciliacion con Gemini

## Impacto actual

Esta deuda puede hacer que:

- el medico sea confundido con el paciente entre fragmentos
- un acompanante cambie de etiqueta
- Gemini pierda una interrupcion muy corta
- los roles dependan demasiado del contenido textual

## Por que se acepta temporalmente

El flujo actual prioriza transcripcion near realtime con baja complejidad:
frontend recorta secciones, `transcription_worker` llama Gemini y FastAPI
consolida `turns[]`. Agregar embeddings/overlap local implica nueva logica de
audio, calibracion clinica y reglas de reconciliacion que todavia no son
necesarias para cerrar el flujo base.

## Owner sugerido

- Frontend audio y recorte: `webapp/src/audio/`
- Contrato estructurado de turnos: `shared/transcription_contract/`
- Worker de transcripcion y reconciliacion con Gemini: `transcription_worker/`
- Persistencia/consolidacion canonica: `backend_fastapi/app/domains/transcription/`

## Trigger para pagarla

Esta deuda debe revisarse cuando ocurra cualquiera de estas condiciones:

- errores frecuentes de speaker label entre secciones en pruebas clinicas
- consultas con acompanantes o interrupciones cortas se vuelvan un caso comun
- se necesite identidad estable de hablantes para resumen, auditoria o copiloto
- Gemini mantenga buena transcripcion literal pero diarizacion inconsistente

## Referencias

- [`../architecture/system-overview.md`](../architecture/system-overview.md)
- [`../decisions/0008-transcripcion-segmentada-near-realtime.md`](../decisions/0008-transcripcion-segmentada-near-realtime.md)
