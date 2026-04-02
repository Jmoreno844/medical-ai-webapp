# ADR-004: Procesamiento Asíncrono de Agentes de IA mediante Cloud Tasks

## Estatus

Propuesto

## Contexto

Actualmente, nuestras interacciones con agentes de IA se gestionan de forma síncrona a través del backend en Cloud Run. El backend realiza llamadas directas a modelos de lenguaje (LLMs) alojados en Cloud Functions.

Esta arquitectura presenta los siguientes riesgos:

- **Timeouts de Conexión:** Los LLMs tienen latencias variables y, en procesos de "autocorrección" (Self-Correction), el tiempo de respuesta puede exceder los límites de una petición HTTP estándar (60-300s).
- **Falta de Resiliencia:** Si la conexión de red falla o el LLM devuelve un error transitorio, la tarea se pierde y el usuario debe reiniciar el proceso manualmente.
- **Experiencia de Usuario (UX) Pobre:** El cliente permanece bloqueado esperando una respuesta, lo que aumenta la percepción de inestabilidad si el proceso es lento.
- **Cumplimiento HIPAA:** Necesitamos asegurar que el rastro de la ejecución y el manejo de errores sean auditables y persistentes.

_Nota importante:_ Este ADR aplica exclusivamente al **workflow de agentes de IA para la detección de códigos**. Por ahora, no se ha decidido si las funciones de transcripción y generación de documentos se migrarán a este nuevo esquema; actualmente continuarán usando su arquitectura base en Cloud Functions.

## Decisión

Hemos decidido implementar un patrón de Procesamiento Asíncrono utilizando Google Cloud Tasks como orquestador de colas y Cloud Run como worker para la ejecución de la lógica del agente.

## Justificación Técnica de Cloud Tasks

- **Gestión de Retries (Robustez):** Cloud Tasks ofrece políticas de reintento configurables con exponential backoff. Si el agente falla por un error de cuota o red, el sistema reintenta automáticamente sin intervención manual.
- **Desacoplamiento:** El backend principal valida la petición, registra el estado inicial en la base de datos (SQL Checkpointing) y delega la ejecución pesada al worker.
- **Escalabilidad Serverless:** Se alinea con nuestra infraestructura actual de GCP, permitiendo escalar a cero cuando no hay tareas, optimizando costos.
- **Seguridad y Cumplimiento:** Cloud Tasks está cubierto por el BAA de Google Cloud para HIPAA. Permite invocar endpoints de Cloud Run mediante OIDC (OpenID Connect), asegurando que solo la cola pueda disparar la ejecución del agente.

## Consecuencias

### Positivas

- **Robustez:** El sistema es tolerante a fallos intermitentes de las APIs de IA.
- **Escalabilidad:** Podemos procesar ráfagas de tareas de agentes sin saturar el backend de usuario.
- **Checkpointing:** Facilita la implementación de una tabla de estados en SQL para que el usuario pueda "reconectar" y ver el progreso de su tarea en tiempo real o diferido.

### Negativas / Retos

- **Complejidad en el Frontend:** El cliente ahora debe realizar polling o usar WebSockets/SSE para conocer el estado de la tarea.
- **Gestión de Idempotencia:** Debemos asegurar que si una tarea se reintenta, el worker pueda manejarlo sin duplicar acciones críticas (como cobros o escrituras duplicadas).

## Alternativas Consideradas

- **Pub/Sub:** Se descartó porque Pub/Sub no permite programar tareas con retrasos específicos ni ofrece una gestión de reintentos tan granular por mensaje individual como Cloud Tasks.
- **LangGraph Cloud:** Se descartó para mantener el control total sobre la residencia de datos y simplificar el cumplimiento HIPAA al no introducir un tercero adicional en el manejo de PHI.

## Notas de Implementación

- **Id de Tarea:** Usa un ID único generado en el backend y guárdalo en tu SQL. Cuando el worker reciba la tarea de Cloud Tasks, usa ese ID para actualizar el registro.
- **Logging:** Asegúrate de que los logs de Cloud Tasks no incluyan el payload si este contiene PHI (datos de pacientes), o que estos logs tengan una política de retención estricta.
