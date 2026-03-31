# 0002. Notificaciones en tiempo real (SSE en memoria)

- Estatus: `Proposed`
- Fecha: `2026-03-31`

## Contexto

El frontend requiere actualizaciones en tiempo real sobre el estado de la transcripcion de audio, que puede tomar entre 20 y 60 segundos, y sobre la generacion de documentos medicos, incluyendo una experiencia tipo maquina de escribir.

Las peticiones HTTP tradicionales pueden hacer timeout o bloquear la interfaz mientras estos procesos siguen ejecutandose.

## Alternativas consideradas

### 1. Polling desde el frontend

Descartado por ahora porque:

- aumenta el numero de requests al backend
- introduce latencia artificial entre actualizaciones
- empeora la experiencia durante la generacion streaming del documento

### 2. Broker compartido (Redis, Kafka, Pub/Sub)

Descartado por ahora porque:

- agrega infraestructura adicional en una etapa temprana
- aumenta costo y complejidad operativa
- todavia no es necesario para la escala actual del producto

## Decision

Implementar `Server-Sent Events (SSE)` nativos utilizando `asyncio.Queue` y un diccionario en memoria (`_channels`) dentro de Django, corriendo bajo ASGI.

En despliegue sobre Cloud Run, restringir el servicio a `max-instances=1` y subir la concurrencia a `max-concurrency=250`.

## Justificacion

### Filosofia "Boring Technology"

Evita introducir piezas de infraestructura adicionales, como Redis o Kafka, en una etapa temprana.

### Costo

$0 adicionales. No requiere pagar por GCP Memorystore (Redis).

### Rendimiento

Latencia cercana a 0 ms al operar estrictamente en la memoria RAM del contenedor.

### Escala actual

Soporta holgadamente el trafico actual y proyectado a corto plazo, en el orden de 1 a 200 medicos concurrentes.

## Consecuencias y riesgos

### Perdida de estado en despliegues

Cuando se despliega una nueva version en Cloud Run, el contenedor se reinicia y todas las conexiones SSE activas se caen.

Mitigacion: el frontend debe tener logica de reconexion automatica.

### Cuello de botella en instancia unica

Todo el trafico HTTP de la aplicacion recae sobre un solo contenedor.

## Trigger de migracion

Esta arquitectura se debe abandonar y refactorizar cuando ocurra alguna de estas condiciones:

- la base de usuarios activos supere aproximadamente los 200 medicos conectados simultaneamente
- la carga de CPU o RAM requiera escalar a `max-instances=2` o mas para evitar latencia en peticiones HTTP normales

## Recordatorio operativo

Recomendacion: quedarse con el modelo por defecto, pero implementar un timeout en el frontend o en `asyncio` para cerrar la conexion SSE si han pasado, por ejemplo, 10 minutos sin actividad.

De lo contrario, un medico que deje el sistema abierto el fin de semana puede mantener la instancia facturando innecesariamente.
