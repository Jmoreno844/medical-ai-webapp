# ADR-008: Transcripcion segmentada near realtime con GCS, Cloud Tasks y Gemini

## Estatus

Propuesto

## Contexto

El flujo actual de transcripcion procesa un audio completo por encuentro: el
navegador sube el archivo a Cloud Storage, FastAPI encola una tarea y la Cloud
Function invoca Gemini. Ese camino es robusto, pero la experiencia no muestra
texto hasta terminar la grabacion y completar la transcripcion completa.

Para una experiencia near realtime queremos que el medico vea avances mientras
habla, sin introducir un canal realtime puro ni enviar audio crudo por FastAPI.
Los segmentos cortos tambien introducen riesgos nuevos: duplicados por overlap,
reintentos duplicados de Cloud Tasks, llegada fuera de orden y recuperacion
cuando el navegador pierde conexion o se cierra.

## Decision

Mantener Cloud Storage como entrada canonica de audio y extender el flujo a
sesiones de transcripcion segmentadas:

```text
Browser mic
  -> VAD o chunks temporales
  -> signed upload URL por segmento
  -> GCS
  -> FastAPI registra metadata idempotente
  -> Cloud Tasks por segmento
  -> FastAPI internal worker transcribe con Gemini async sobre Vertex AI
  -> SSE publica segment_text si el cliente esta conectado
  -> Cloud Task final consolida los textos ordenados
```

El navegador conserva una cola local en IndexedDB hasta que FastAPI confirme que
el segmento quedo registrado. A partir de ese punto, los estados y reintentos de
transcripcion son responsabilidad del backend y Cloud Tasks.

## Contrato de segmentos

Cada segmento debe tener un identificador estable generado antes de subirlo:

- `recording_session_id`: identifica la grabacion activa dentro del encuentro.
- `client_segment_id`: UUID generado por el navegador; se usa para idempotencia
  entre retries del frontend.
- `segment_index`: entero monotono dentro de la sesion; se usa para ordenar.
- `start_time_ms` y `end_time_ms`: offsets relativos al inicio de la grabacion.
- `gcs_object_name`: objeto subido al bucket de audio.
- `duration_ms`, `content_type`, `byte_size` cuando esten disponibles.
- `status`, `retry_count`, `raw_transcript`, `error_code`.

El backend debe imponer unicidad por segmento. La restriccion minima es:

```text
UNIQUE(recording_session_id, client_segment_id)
```

Tambien se recomienda evitar indices repetidos dentro de una misma sesion:

```text
UNIQUE(recording_session_id, segment_index)
```

## Idempotencia y Cloud Tasks

Cloud Tasks puede entregar la misma tarea mas de una vez. Por eso el endpoint que
procesa un segmento debe ser idempotente:

1. Cargar el segmento por `segment_id` o por `(recording_session_id,
   client_segment_id)`.
2. Si el segmento ya esta `transcribed`, devolver exito sin llamar a Gemini.
3. Si esta `transcribing` desde hace poco, devolver exito o conflicto controlado
   segun el mecanismo de lock elegido.
4. Si esta pendiente o fallo de forma reintentable, marcar `transcribing`,
   llamar a Gemini y guardar `raw_transcript`.
5. Guardar errores transitorios como `failed_retryable` para que Cloud Tasks
   pueda reintentar; guardar errores definitivos como `failed_final`.

El worker interno no debe crear segmentos nuevos ni decidir orden. FastAPI y
PostgreSQL son la fuente de verdad.

## Orden

No se debe confiar en el orden de llegada de uploads, callbacks o eventos SSE.
Toda vista continua y toda consolidacion final deben ordenar por:

```sql
ORDER BY segment_index ASC
```

`start_time_ms` y `end_time_ms` sirven como respaldo diagnostico y para detectar
huecos o solapes inesperados, pero `segment_index` es el orden logico de la
sesion.

## Overlap, pre-roll y tail

Para MVP se acepta segmentar con chunks temporales, por ejemplo `15s` con `2s`
de overlap. Para produccion clinica se prefiere VAD en el navegador:

- cerrar segmento despues de una pausa natural;
- incluir `500-800ms` de pre-roll;
- incluir `700-1000ms` de tail;
- forzar corte si el segmento supera `15-25s`;
- usar `1-2s` de overlap solo en cortes forzados.

El overlap protege cortes artificiales, pero produce texto duplicado. Por eso
cada segmento conserva su `raw_transcript` y la union visible se considera
preliminar hasta la consolidacion.

## Deduplicacion y consolidacion

El backend debe aplicar deduplicacion ligera al unir segmentos para la vista
preliminar. La deduplicacion no debe interpretar hechos clinicos; solo debe
remover repeticiones obvias en el borde entre segmentos, por ejemplo:

```text
Segmento 1: "El paciente refiere dolor abdominal desde ayer."
Segmento 2: "desde ayer. Niega fiebre."
Union:      "El paciente refiere dolor abdominal desde ayer. Niega fiebre."
```

La consolidacion final se ejecuta sobre los `raw_transcript` ordenados. El prompt
de Gemini debe indicar explicitamente:

```text
Une los segmentos en una sola transcripcion.
Elimina frases o palabras repetidas causadas por audio solapado.
Mejora solo puntuacion y continuidad textual.
No resumas, no agregues, no omitas y no cambies hechos clinicos.
Conserva dudas o partes inaudibles como [inaudible].
```

Si faltan segmentos o hay segmentos en `failed_final`, la sesion no debe marcarse
como final limpia automaticamente. Debe quedar en un estado revisable, con los
huecos visibles para el medico.

## Recuperacion del frontend

El frontend maneja solo la parte previa a la confirmacion del servidor:

- grabar segmento;
- guardarlo en IndexedDB;
- solicitar signed URL;
- subir a GCS;
- registrar metadata en FastAPI;
- reintentar con backoff mientras el segmento no este registrado.

El audio local no debe borrarse hasta que FastAPI confirme el registro durable
del segmento. Si el usuario cierra la pagina, al volver al encuentro la SPA debe
leer IndexedDB, detectar segmentos pendientes y reanudar la subida.

Una vez registrado el segmento, el frontend deja de reintentar transcripcion.
Desde ese punto, Cloud Tasks y el backend manejan retries, estados y
consolidacion.

## Alternativas consideradas

### Enviar audio corto directo a FastAPI/Gemini

Reduce uno o varios saltos de latencia, pero hace el flujo mas fragil: FastAPI
carga binarios, aumenta el riesgo de timeouts, se pierde recuperacion durable y
se dificulta reprocesar segmentos. Se descarta para produccion clinica.

### Usar solo chunks con overlap

Es aceptable para validar Gemini rapido, pero no para el camino final de
produccion. Corta frases con mas frecuencia, duplica texto y exige
deduplicacion mas agresiva. El camino de produccion debe evolucionar a VAD con
pre-roll/tail y overlap solo en cortes forzados.

### Redis como cola principal

Redis podria ayudar a SSE multi-instancia o pub/sub futuro, pero no reemplaza
tan directamente el patron ya aceptado de Cloud Tasks para trabajos HTTP
durables. Para transcripcion segmentada se mantiene Cloud Tasks.

### Cloud Function como worker de transcripcion

Fue el patrón original para audio completo, pero la primera version segmentada
mantiene el worker dentro de FastAPI para reducir piezas operativas. La llamada
a Gemini debe usar el Google Gen AI SDK async; no se debe usar
`vertexai.generative_models` dentro del backend.

## Consecuencias

### Positivas

- El audio sigue entrando por Cloud Storage, alineado con el flujo existente.
- FastAPI mantiene requests cortos y no procesa binarios pesados.
- Cloud Tasks aporta retries, backoff e invocacion autenticada.
- La UI puede mostrar progreso near realtime sin depender de WebSocket.
- La transcripcion final puede reconstruirse de forma ordenada y auditable.

### Negativas / retos

- Requiere nuevas tablas o campos para sesiones y segmentos.
- Requiere cola local en IndexedDB y reanudacion en frontend.
- La deduplicacion debe ser conservadora para no alterar contenido clinico.
- La consolidacion final debe manejar segmentos faltantes o fallidos.
- El volumen de tasks y objetos GCS crece con segmentos cortos.

## Notas de implementacion

- Los endpoints de registro de segmento deben ser idempotentes.
- Los callbacks desde Cloud Functions deben actualizar segmentos existentes, no
  crear nuevas filas.
- Los eventos SSE son solo notificaciones live; el estado recuperable vive en
  PostgreSQL y en la cola local del navegador antes del registro.
- IndexedDB borra el blob local cuando FastAPI confirma el registro durable de
  la seccion; GCS conserva el objeto hasta la lifecycle policy de 7 dias salvo
  DELETE explicito.
- Los logs no deben incluir audio, transcripts completos, tokens ni secretos.
- La documentacion de base de datos debe actualizarse junto con la migracion que
  introduzca las tablas de sesiones/segmentos.
