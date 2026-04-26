# ADR-003: Procesamiento Asíncrono de Audio mediante Google Cloud Tasks

## Estatus

Aceptado

## Contexto

Las consultas médicas en la plataforma generan audios de larga duración (10 a 30 minutos). Aunque modelos multimodales como Gemini 1.5/2.0 Flash procesan estos archivos con una velocidad asombrosa (~20-40 segundos para un audio de 15 minutos), este tiempo sigue siendo excesivo para el ciclo de vida de una petición HTTP estándar en el backend.

## Decisión

Implementar Google Cloud Tasks como el orquestador y buffer entre el backend
(FastAPI) y el worker de transcripción. En la fase actual el target de las
tareas de transcripción es un endpoint interno de FastAPI, que llama a Gemini
mediante el Google Gen AI SDK async sobre Vertex AI usando referencias `gs://`.
Cloud Functions queda para generación documental.

El backend encola la tarea y libera la conexión del usuario de inmediato con un
estado 200 OK (Processing).

## Justificación Técnica (El "Por Qué")

### 1. Prevención del "Worker Starvation" (Hambruna de Procesos)

En un servidor web (FastAPI), cada petición activa ocupa un "worker" o hilo de ejecución.

- **El Problema**: Si 10 médicos guardan una consulta al mismo tiempo y FastAPI hace una llamada síncrona a la IA, esos 10 workers quedan bloqueados por 40 segundos esperando respuesta.
- **El Riesgo**: Si el servidor tiene un límite de 10-20 workers, la aplicación dejará de responder a cualquier otro usuario (incluso para ver una agenda o hacer login) porque todos los hilos están "secuestrados" esperando a la IA.
- **La Solución**: Cloud Tasks permite que el request del usuario termine en
  milisegundos. El worker interno de FastAPI queda protegido por límites de
  concurrencia de la cola (`max_concurrent_dispatches`) y debe usar llamadas
  async reales al SDK de Gemini.

### 2. Gestión de Timeouts de Red

Las conexiones HTTP en la nube (especialmente tras balanceadores o en entornos serverless) tienen límites de tiempo estrictos (usualmente 30-60 segundos).

- **El Riesgo**: Si la transcripción se demora un poco más de lo habitual por
  carga en la API de Google, una conexión síncrona del usuario podría romperse
  por timeout, dejando la historia clínica en un estado inconsistente (audio
  subido pero nunca transcrito).
- **La Solución**: Cloud Tasks es agnóstico al tiempo de respuesta del destino; si la tarea se toma 2 minutos, la tarea sigue viva hasta que recibe una confirmación de éxito.

### 3. Resiliencia y Retries Automáticos (Backoff)

Las APIs de IA pueden fallar ocasionalmente (errores 500, cuotas excedidas, etc.).

- **El Problema**: En un flujo síncrono, si la llamada falla, el médico ve un error y pierde el progreso o debe reintentar manualmente.
- **La Solución**: Cloud Tasks tiene una política de reintentos con Exponencial
  Backoff. Si el worker interno falla, la tarea se reintenta automáticamente
  segundos o minutos después sin intervención humana ni del médico.

### 4. Autenticación Robusta (OIDC Tokens)

Manejar la seguridad entre servicios puede ser complejo.

- **La Ventaja**: Cloud Tasks permite usar Service Account Impersonation. La
  tarea se empaqueta con un token OIDC que el endpoint interno de FastAPI valida
  contra la service account invocadora. Esto elimina la necesidad de manejar
  llaves API o JWTs manuales propensos a errores en la capa de transporte.

## Consecuencias

- **Positivas**: El request del usuario es ligero y rápido; la interfaz de usuario nunca se bloquea; los reintentos quedan centralizados en Cloud Tasks.
- **Negativas**: Introduce una ligera complejidad adicional en el despliegue (se debe crear la cola en GCP); requiere que el frontend maneje estados de "Procesando" mediante polling o SSE.

## Retención y SSE

- La signed URL de subida de audio dura 10 minutos.
- `audio_expires_at` en el flujo legacy es una expiración lógica de acceso de
  24 horas.
- El borrado real del blob en GCS ocurre por lifecycle del bucket a los 7 días,
  salvo DELETE explícito del médico.
- SSE no borra audio ni cambia retención; solo notifica progreso o éxito.
