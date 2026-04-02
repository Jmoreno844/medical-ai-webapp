# ADR-003: Procesamiento Asíncrono de Audio mediante Google Cloud Tasks

## Estatus

Aceptado

## Contexto

Las consultas médicas en la plataforma generan audios de larga duración (10 a 30 minutos). Aunque modelos multimodales como Gemini 1.5/2.0 Flash procesan estos archivos con una velocidad asombrosa (~20-40 segundos para un audio de 15 minutos), este tiempo sigue siendo excesivo para el ciclo de vida de una petición HTTP estándar en el backend.

## Decisión

Implementar Google Cloud Tasks como el orquestador y buffer entre el backend (Django) y el servicio de transcripción (Cloud Functions). El backend encola la tarea y libera la conexión del usuario de inmediato con un estado 200 OK (Processing).

## Justificación Técnica (El "Por Qué")

### 1. Prevención del "Worker Starvation" (Hambruna de Procesos)

En un servidor web (Django), cada petición activa ocupa un "worker" o hilo de ejecución.

- **El Problema**: Si 10 médicos guardan una consulta al mismo tiempo y Django hace una llamada síncrona a la IA, esos 10 workers quedan bloqueados por 40 segundos esperando respuesta.
- **El Riesgo**: Si el servidor tiene un límite de 10-20 workers, la aplicación dejará de responder a cualquier otro usuario (incluso para ver una agenda o hacer login) porque todos los hilos están "secuestrados" esperando a la IA.
- **La Solución**: Cloud Tasks permite que Django delegue el trabajo y quede libre en milisegundos para atender a otros médicos.

### 2. Gestión de Timeouts de Red

Las conexiones HTTP en la nube (especialmente tras balanceadores o en entornos serverless) tienen límites de tiempo estrictos (usualmente 30-60 segundos).

- **El Riesgo**: Si la transcripción se demora un poco más de lo habitual por carga en la API de Google, la conexión entre Django y la Cloud Function se romperá por timeout, dejando la historia clínica en un estado inconsistente (audio subido pero nunca transcrito).
- **La Solución**: Cloud Tasks es agnóstico al tiempo de respuesta del destino; si la tarea se toma 2 minutos, la tarea sigue viva hasta que recibe una confirmación de éxito.

### 3. Resiliencia y Retries Automáticos (Backoff)

Las APIs de IA pueden fallar ocasionalmente (errores 500, cuotas excedidas, etc.).

- **El Problema**: En un flujo síncrono, si la llamada falla, el médico ve un error y pierde el progreso o debe reintentar manualmente.
- **La Solución**: Cloud Tasks tiene una política de reintentos con Exponencial Backoff. Si la Cloud Function falla, la tarea se reintenta automáticamente segundos o minutos después sin intervención humana ni del médico.

### 4. Autenticación Robusta (OIDC Tokens)

Manejar la seguridad entre servicios puede ser complejo.

- **La Ventaja**: Cloud Tasks permite usar Service Account Impersonation. La tarea se empaqueta con un token OIDC que solo la Cloud Function puede validar. Esto elimina la necesidad de manejar llaves API o JWTs manuales propensos a errores en la capa de transporte.

## Consecuencias

- **Positivas**: El backend es extremadamente ligero y rápido; la interfaz de usuario nunca se bloquea; los costos de Cloud Run se mantienen bajos al no tener instancias "ociosas" esperando respuestas externas.
- **Negativas**: Introduce una ligera complejidad adicional en el despliegue (se debe crear la cola en GCP); requiere que el frontend maneje estados de "Procesando" mediante polling o SSE.
