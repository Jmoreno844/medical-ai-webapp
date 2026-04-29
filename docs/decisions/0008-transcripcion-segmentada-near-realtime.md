# ADR-008: Transcripcion por secciones near realtime con GCS, Cloud Tasks y Gemini

## Estatus

Aceptado

## Contexto

El flujo actual de transcripcion procesa un audio completo por encuentro: el
navegador sube el archivo a Cloud Storage, FastAPI encola una tarea y la Cloud
Function invoca Gemini. Ese camino es robusto, pero la experiencia no muestra
texto hasta terminar la grabacion y completar la transcripcion completa.

Para una experiencia near realtime queremos que el medico vea avances mientras
habla, sin introducir un canal realtime puro ni enviar audio crudo por FastAPI.
Las secciones cortas tambien introducen riesgos nuevos: duplicados por overlap,
reintentos duplicados de Cloud Tasks, llegada fuera de orden y recuperacion
cuando el navegador pierde conexion o se cierra.

## Decision

Mantener Cloud Storage como entrada canonica de audio y extender el flujo a
sesiones de transcripcion por secciones:

```text
Browser mic
  -> VAD en navegador + blobs WebM independientes por seccion
  -> IndexedDB local
  -> signed upload URL por seccion
  -> GCS
  -> FastAPI registra metadata idempotente
  -> Cloud Tasks por seccion hacia transcription_worker
  -> transcription_worker corre Silero ONNX VAD y Gemini async sobre Vertex AI
  -> FastAPI recibe callback saneado, persiste estado y publica SSE
  -> SSE publica updates parciales si el cliente esta conectado
  -> FastAPI finaliza uniendo textos ordenados por section_index
```

El navegador conserva una cola local en IndexedDB hasta que FastAPI confirme que
la seccion quedo registrada. A partir de ese punto, los estados y reintentos de
transcripcion son responsabilidad del backend y Cloud Tasks.

## Estado implementado

La primera version operativa mantiene SSE en memoria y ya corre con VAD ligero
en el navegador:

- Backend FastAPI crea sesiones, emite signed URLs por seccion, registra
  secciones de forma idempotente, finaliza grabaciones y expone status de sesion.
- PostgreSQL tiene `transcription_recording_session` y
  `transcription_audio_section` con unicidad por
  `(recording_session_id, client_section_id)` y por
  `(recording_session_id, section_index)`.
- Cloud Tasks apunta a `transcription_worker`, un Cloud Run privado que descarga
  la seccion desde GCS, ejecuta Silero ONNX VAD, llama Gemini async mediante
  `google-genai` solo cuando hay habla y devuelve callbacks saneados a FastAPI.
  En desarrollo local, FastAPI puede llamar ese worker mediante
  `TRANSCRIPTION_WORKER_BASE_URL` sin emulador de Cloud Tasks.
- FastAPI guarda `raw_transcript`, evita procesar de nuevo si una seccion ya
  esta `transcribed` o `discarded_no_speech` y publica `transcription_update`
  por SSE. El modelo por defecto de transcripcion es `gemini-2.5-flash` con
  `VERTEX_AI_LOCATION=global`.
- Ademas del `raw_transcript` por seccion, FastAPI sincroniza el merge parcial
  en `document.content_markdown` durante la sesion para que un refresh o
  reconexion recupere el ultimo texto realtime aunque el SSE en memoria se haya
  perdido. La finalizacion deterministica deja el contenido canonico definitivo.
- La finalizacion ordena por `section_index`, une los textos no vacios y aplica
  deduplicacion ligera de overlap sin una llamada adicional a Gemini.
- El frontend graba blobs WebM independientes por seccion, usa VAD basado en
  Web Audio para cerrar por pausa natural, mantiene un maximo forzado de `25s`,
  usa `overlap_ms=1500` solo en cortes forzados, guarda blobs pendientes en
  IndexedDB, reintenta al abrir/reconectar, borra el blob local solo despues
  del registro durable en FastAPI y conserva el flujo legacy de audio completo
  como fallback/migracion.
- Infraestructura deja la transcripcion en FastAPI/Cloud Tasks y la generacion
  documental en `document_generation_worker`; Cloud Functions queda solo para
  transcripcion legacy.

## Contrato de secciones

Cada seccion debe tener un identificador estable generado antes de subirla:

- `recording_session_id`: identifica la grabacion activa dentro del encuentro.
- `client_section_id`: UUID generado por el navegador; se usa para idempotencia
  entre retries del frontend.
- `section_index`: entero monotono dentro de la sesion; se usa para ordenar.
- `start_time_ms` y `end_time_ms`: offsets relativos al inicio de la grabacion.
- `gcs_object_name`: objeto subido al bucket de audio.
- `duration_ms`, `content_type`, `byte_size` cuando esten disponibles.
- `status`, `retry_count`, `raw_transcript`, `error_code`.

El backend debe imponer unicidad por seccion. La restriccion minima es:

```text
UNIQUE(recording_session_id, client_section_id)
```

Tambien se recomienda evitar indices repetidos dentro de una misma sesion:

```text
UNIQUE(recording_session_id, section_index)
```

## Idempotencia y Cloud Tasks

Cloud Tasks puede entregar la misma tarea mas de una vez. Por eso el endpoint que
procesa una seccion debe ser idempotente:

1. Cargar la seccion por `section_id` o por `(recording_session_id,
client_section_id)`.
2. Si la seccion ya esta `transcribed`, devolver exito sin llamar a Gemini.
3. Si esta `transcribing` desde hace poco, devolver exito o conflicto controlado
   segun el mecanismo de lock elegido.
4. Si esta pendiente o fallo de forma reintentable, marcar `transcribing`,
   llamar a Gemini y guardar `raw_transcript`.
5. Guardar errores transitorios como `failed_retryable` para que Cloud Tasks
   pueda reintentar; guardar errores definitivos como `failed_final`.

El worker interno no debe crear secciones nuevas ni decidir orden. FastAPI y
PostgreSQL son la fuente de verdad.

## Orden

No se debe confiar en el orden de llegada de uploads, callbacks o eventos SSE.
Toda vista continua y toda finalizacion deben ordenar por:

```sql
ORDER BY section_index ASC
```

`start_time_ms` y `end_time_ms` sirven como respaldo diagnostico y para detectar
huecos o solapes inesperados, pero `section_index` es el orden logico de la
sesion.

## Overlap, pre-roll y tail

El frontend actual mantiene blobs WebM independientes por seccion. Esto evita
enviar a Gemini recortes internos de un WebM continuo, porque despues del
primer recorte pueden faltar metadatos del contenedor y Vertex puede responder
`Failed to decode audio or visual data`. El corte principal ya usa VAD en el
navegador con estos parametros operativos:

- `pre-roll`: `650ms` como ventana de pausa confirmada antes de rearmar una nueva seccion;
- `tail`: `900ms` antes de cerrar por pausa natural;
- `duracion minima por seccion`: `1000ms`;
- `maximo forzado`: `25000ms` si no aparece una pausa util;
- `overlap forzado`: `1500ms` solo cuando se supera ese maximo;
- `fallback por tiempo`: `20000ms` si el VAD no puede inicializarse.

El overlap protege cortes artificiales, pero produce texto duplicado. Por eso
cada seccion conserva su `raw_transcript` y la union visible se considera
preliminar hasta la finalizacion de la sesion.

## Deduplicacion y finalizacion

El backend aplica deduplicacion ligera al unir secciones para la vista
preliminar. La deduplicacion no debe interpretar hechos clinicos; solo debe
remover repeticiones obvias en el borde entre secciones, por ejemplo:

```text
Seccion 1: "El paciente refiere dolor abdominal desde ayer."
Seccion 2: "desde ayer. Niega fiebre."
Union:      "El paciente refiere dolor abdominal desde ayer. Niega fiebre."
```

La finalizacion se ejecuta en FastAPI sobre los `raw_transcript` ordenados. No
hace una segunda llamada a Gemini; solo une textos no vacios con la misma
deduplicacion ligera de overlap.

Antes de alimentar la vista realtime y la finalizacion, FastAPI aplica
una normalizacion textual conservadora sobre una copia derivada del
`raw_transcript`:

- elimina chunks no lexicos que sean solo tags removibles como `[tos]`,
  `[ruido]`, `[silencio]`, `[carraspeo]` o `[respiracion]`;
- elimina esos mismos tags cuando aparezcan inline dentro de una frase, por
  ejemplo `Paciente refiere dolor [tos] desde ayer` -> `Paciente refiere dolor
desde ayer`;
- conserva `raw_transcript` original por seccion para debugging y reprocess;
- conserva tags de incertidumbre como `[inaudible]` en la salida derivada,
  porque si aportan informacion clinica u operativa.

Si faltan secciones o hay secciones en `failed_final`, la sesion no debe
marcarse como final limpia automaticamente. Debe quedar en un estado revisable,
con los huecos visibles para el medico.

## Recuperacion del frontend

El frontend maneja solo la parte previa a la confirmacion del servidor:

- grabar seccion;
- guardarla en IndexedDB;
- solicitar signed URL;
- subir a GCS;
- registrar metadata en FastAPI;
- reintentar con backoff mientras la seccion no este registrada.

El audio local no debe borrarse hasta que FastAPI confirme el registro durable
de la seccion. Si el usuario cierra la pagina, al volver al encuentro la SPA
debe leer IndexedDB, detectar secciones pendientes y reanudar la subida.

Una vez registrada la seccion, el frontend deja de reintentar transcripcion.
Desde ese punto, Cloud Tasks y el backend manejan retries, estados y
finalizacion.

## Alternativas consideradas

### Enviar audio corto directo a FastAPI/Gemini

Reduce uno o varios saltos de latencia, pero hace el flujo mas fragil: FastAPI
carga binarios, aumenta el riesgo de timeouts, se pierde recuperacion durable y
se dificulta reprocesar secciones. Se descarta para produccion clinica.

### Usar solo chunks con overlap

Es aceptable para validar Gemini rapido, pero ahora queda solo como fallback si
el VAD del navegador falla al inicializar. Corta frases con mas frecuencia,
duplica texto y exige deduplicacion mas agresiva.

### Redis como cola principal

Redis podria ayudar a SSE multi-instancia o pub/sub futuro, pero no reemplaza
tan directamente el patron ya aceptado de Cloud Tasks para trabajos HTTP
durables. Para transcripcion por secciones se mantiene Cloud Tasks.

### Cloud Function como worker de transcripcion

Fue el patrón original para audio completo. Para secciones near realtime se
prefiere Cloud Run porque permite empaquetar ONNX/ffmpeg, controlar concurrencia
por contenedor y mantener paridad local con Docker. La llamada a Gemini debe
usar el Google Gen AI SDK async; no se debe usar `vertexai.generative_models`.

### Worker Cloud Run dedicado

La version actual mueve VAD y Gemini de transcripcion a
`transcription_worker` para aislar CPU/dependencias ONNX y permitir escala
independiente del backend, que sigue limitado por SSE en memoria. FastAPI
conserva la base de datos, merge canonico, callbacks y SSE.

## Consecuencias

### Positivas

- El audio sigue entrando por Cloud Storage, alineado con el flujo existente.
- FastAPI mantiene requests cortos y no procesa binarios pesados.
- Cloud Tasks aporta retries, backoff e invocacion autenticada.
- La UI puede mostrar progreso near realtime sin depender de WebSocket.
- La transcripcion final puede reconstruirse de forma ordenada y auditable.

### Negativas / retos

- Requiere nuevas tablas o campos para sesiones y secciones.
- Requiere cola local en IndexedDB y reanudacion en frontend.
- La deduplicacion debe ser conservadora para no alterar contenido clinico.
- La finalizacion debe manejar secciones faltantes o fallidas.
- El volumen de tasks y objetos GCS crece con secciones cortas.

## Notas de implementacion

- Los endpoints de registro de seccion deben ser idempotentes.
- Los endpoints internos de Cloud Tasks deben actualizar secciones existentes, no
  crear nuevas filas.
- El worker dedicado no debe escribir directamente en PostgreSQL ni publicar SSE;
  debe devolver callbacks saneados a FastAPI.
- Los eventos SSE son solo notificaciones live; el estado recuperable vive en
  PostgreSQL y en la cola local del navegador antes del registro.
- IndexedDB borra el blob local cuando FastAPI confirma el registro durable de
  la seccion; GCS conserva el objeto hasta la lifecycle policy de 7 dias salvo
  DELETE explicito.
- Los logs no deben incluir audio, transcripts completos, tokens ni secretos.
- La documentacion de base de datos debe actualizarse junto con migraciones que
  cambien las tablas de sesiones/secciones.

## Trabajo pendiente

- **Afinar VAD clinico:** calibrar umbrales RMS/peak y validar los bordes con
  grabaciones largas, cifras, lateralidad y negaciones clinicas.
- **Redis o broker compartido para SSE:** antes de subir Cloud Run a multiples
  instancias, mover el hub SSE en memoria a Redis, Pub/Sub u otro broker.
- **E2E real en GCP:** validar en staging signed URLs reales, subida a GCS,
  Cloud Tasks, OIDC de tareas, Vertex AI con `google-genai` y SSE durante una
  transcripcion real.
- **UX de recuperacion:** pulir pantallas para audio pendiente, boton de
  reintento, estados visibles de seccion fallida y recuperacion tras refresh o
  cierre de pestana.
- **Deduplicacion mas fuerte:** evaluar similitud de texto mas robusta para
  overlaps clinicos sin alterar hechos.
- **Observabilidad:** agregar logs estructurados por `session_id` / `section_id`,
  metricas de tiempo por seccion, costo aproximado por consulta y alertas de
  secciones fallidas.
- **Limites operativos:** definir rate limits por medico/encuentro, tamano maximo
  por seccion, duracion maxima de sesion y cleanup de sesiones abandonadas.
