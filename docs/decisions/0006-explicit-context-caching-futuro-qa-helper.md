# ADR-006: Diferir Explicit Context Caching para un Futuro QA Helper Clínico

## Estatus

Aceptado

## Contexto

El runtime actual del copiloto está centrado en el `document helper`: una conversación lateral para leer contexto del encounter y preparar `patch -> review -> apply` sobre un documento target. En este flujo, el médico normalmente permanece dentro del mismo chat mientras edita o pregunta sobre el documento actual.

Vertex AI ya ofrece `implicit caching` por defecto. Ese mecanismo favorece conversaciones continuas con prefijos similares y es suficiente para el slice actual siempre que:

- el chat se mantenga append-only
- no se reescriban mensajes pasados para "actualizar" transcripciones previas
- el armado del prompt conserve un orden determinista en el bloque estable del contexto

Se evaluó implementar `explicit context caching` en el runtime del `document helper`, pero se descartó por ahora porque añade complejidad operativa real:

- TTL e invalidación por paciente/encounter/context pack
- persistencia y lookup de `cache_name`
- costo y manejo de PHI cacheada
- restricciones del request shape cuando se usa `cached_content`

## Decisión

No implementaremos `explicit context caching` en el `document helper` actual.

En esta fase, el runtime debe apoyarse en:

- continuidad del mismo chat
- `implicit caching` del proveedor
- construcción determinista del contexto
- estrategia append-only para chunks/transcripción incremental

El `explicit caching` se reconsiderará únicamente para un futuro **QA helper clínico** cuando exista un corpus pesado y estable reutilizable entre varias preguntas o incluso entre varias superficies de chat.

## Casos futuros donde sí podría aportar

1. **Reuso entre superficies o chats distintos**
   - Ejemplo: el médico usa primero el side helper durante la consulta y luego abre una página de chat clínico completa.
   - El mismo pack de PDFs e historia longitudinal debe seguir disponible aunque cambie la conversación o el wrapper del prompt.
   - Aquí `implicit caching` ya no tiene garantía de hit porque cambia el hilo y el prefijo compartido.

2. **Chats muy largos que requieran summarization o reinicio**
   - Ejemplo: una conversación de QA clínico crece tanto que conviene resumir o compactar el chat.
   - Aunque el historial cambie, sigue existiendo un bloque estable de contexto clínico pesado que conviene reutilizar.
   - `Explicit caching` permite preservar ese pack sin depender del prefijo exacto del chat previo.

3. **Consulta pausada y retomada después**
   - Ejemplo: el médico consulta ahora, vuelve horas después con nuevas preguntas y quiere seguir usando los mismos PDFs, antecedentes o labs previos.
   - `Implicit caching` depende de cercanía temporal y gran similitud del request; no da control sobre esa reutilización.

## Casos donde no justifica la complejidad

- Un único chat continuo de edición documental.
- Varias preguntas seguidas dentro del mismo hilo del `document helper`.
- Escenarios donde el médico puede formular varias dudas en un solo prompt y obtener una sola respuesta estructurada.

## Lineamientos para el futuro diseño

- El bloque candidato a `explicit caching` debe ser un **stable context pack**, no la transcripción viva.
- Ejemplos de contenido cacheable a futuro:
  - PDFs subidos por el médico
  - resumen longitudinal del paciente
  - antecedentes relevantes
  - labs previos
  - documentos históricos seleccionados
- La transcripción incremental en realtime debe seguir como eventos/chunks nuevos, no como reemplazo retroactivo de mensajes pasados.
- Antes de introducir `explicit caching`, se debe maximizar `implicit caching`:
  - prefijo estable
  - orden fijo de fuentes
  - payload append-only

## Consecuencias

### Positivas

- Menos complejidad y menos riesgo en el slice actual del `document helper`.
- Se evita cachear PHI explícitamente sin una necesidad de producto ya validada.
- Se mantiene el runtime actual enfocado en lectura progresiva y writer flow seguro.

### Negativas / Retos

- El futuro QA helper no podrá reutilizar automáticamente un pack pesado entre chats o superficies diferentes hasta que se implemente esta capacidad.
- Si el producto evoluciona hacia consultas longitudinales más pesadas, habrá que introducir una capa adicional de lifecycle e invalidación de caches.
