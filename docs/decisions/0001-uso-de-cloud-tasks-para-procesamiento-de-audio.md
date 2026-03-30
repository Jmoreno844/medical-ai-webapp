# 0001. Uso de Cloud Tasks para procesamiento de audio

- Estatus: `Proposed`
- Fecha: `2026-03-29`

## Contexto

Necesitamos transcribir audios largos con Gemini. El flujo actual inicia la transcripcion desde Django mediante una llamada HTTP directa a una Cloud Function y espera la respuesta dentro del request web.

Ese enfoque aumenta el riesgo de:

- timeouts en el request original
- bloqueo innecesario del backend mientras la IA procesa el audio
- falta de reintentos confiables ante errores transitorios
- fragilidad operativa si el trabajo tarda demasiado o si hay picos de carga

Ademas, este sistema esta desplegado sobre servicios orientados a escalar horizontalmente y sin estado compartido, por lo que conviene desacoplar el trabajo pesado del ciclo request-response del usuario.

## Alternativas consideradas

### 1. Llamada HTTP directa Django -> Cloud Function

Descartada por:

- falta de reintentos gestionados por infraestructura
- mayor riesgo de timeout
- peor experiencia de usuario si el request tarda demasiado
- mayor acoplamiento entre el request web y el procesamiento de IA

### 2. Pub/Sub

Descartado por ahora porque:

- el caso de uso actual es 1-a-1, no fan-out
- necesitamos mejor control de velocidad y dispatch
- Cloud Tasks encaja mejor para invocar handlers HTTP concretos con retries

## Decision

Usar `Cloud Tasks` como intermediario entre Django y el procesamiento de transcripcion.

El flujo esperado sera:

1. Django valida permisos, audio y documento.
2. Django crea una task con el payload minimo necesario.
3. Cloud Tasks despacha la solicitud al handler HTTP encargado de la transcripcion.
4. El handler procesa el audio con Gemini.
5. Al finalizar, el handler actualiza Django por callback autenticado.

## Consecuencias

### Positivas

- reintentos automaticos ante errores transitorios
- mejor control de flujo y rate limiting
- menor riesgo de timeout en requests del usuario
- arquitectura mas robusta para cargas variables
- mejor base para crecer en el mediano plazo

### Negativas

- pequena latencia adicional al inicio del proceso
- configuracion adicional en Google Cloud
- necesidad de disenar handlers idempotentes
- mayor complejidad operativa que una llamada HTTP directa

## Notas

Cuando esta decision se implemente en produccion, el estatus de este ADR deberia cambiar de `Proposed` a `Accepted`.
