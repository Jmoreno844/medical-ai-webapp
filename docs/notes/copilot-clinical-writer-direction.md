# Direccion Actual del Copilot Writer Clinico

Nota de trabajo para fijar lo que ya parece bastante claro sobre el escritor documental del copiloto mientras seguimos iterando producto.

No reemplaza una ADR. Resume criterios provisionales para no perder acuerdos en conversaciones largas.

## Contexto

El producto se esta pensando como una especie de `GitHub Copilot Chat` para medicos:

- conversa sobre el encounter y sus documentos
- propone cambios en documentos clinicos
- mantiene `human in the loop` via `patch -> review -> apply`
- debe ser especialmente cuidadoso con razonamiento medico, trazabilidad y no invencion de datos

El writer actual ya puede leer documentos y proponer patch sets, pero aparecieron casos donde el cambio no es solo textual sino clinico y contextual.

---

## Decisiones cerradas

### 1. No todos los cambios son del mismo tipo

Tres clases de trabajo del writer:

1. `local edit`
   - typo, traduccion puntual, insercion corta, borrado acotado
   - normalmente basta uno o pocos patches locales

2. `clinical fact propagation`
   - entra un nuevo dato clinico que debe reflejarse en varias secciones
   - ejemplos: embarazo, alergia relevante, anticoagulacion, nuevo sintoma importante
   - el agente debe leer la nota completa y proponer un `patch set` multipatch coherente

3. `clinical reinterpretation`
   - el nuevo dato cambia analisis, impresion, riesgo o plan
   - aqui no basta "parchar una frase"; hace falta razonamiento estructurado antes de redactar

### 2. El writer si deberia poder tocar analisis y plan

Cuando el nuevo dato cambia claramente el riesgo o el significado clinico del caso, el writer no deberia limitarse a actualizar solo la seccion textual mas obvia.

En estos casos si deberia poder ajustar:

- enfermedad actual
- antecedentes relevantes
- impresion diagnostica
- analisis clinico
- plan

Siempre con estas restricciones:

- no inventar examenes, tratamientos o resultados no mencionados
- no sobreespecificar conductas si el contexto no lo permite
- subir el nivel de cautela cuando aplique
- dejar que el medico mantenga el control final a traves del review del patch set

### 3. El human in the loop principal sigue siendo el review

No meter una pregunta intermedia obligatoria caso por caso.

- el agente puede proponer automaticamente los cambios clinicamente necesarios
- el review del patch set es el `human in the loop` principal
- solo pedir aclaracion si hay varias interpretaciones razonables o falta conocimiento que no esta en la nota

### 4. El writer necesita pensar en coherencia por secciones

Las secciones son **regiones semanticas dentro del texto plano**, no una entidad en el modelo de datos.
Los documentos se almacenan como un solo campo `TextField`, sin particion estructural.
El LLM debe identificar las secciones relevantes leyendo la nota completa.

En cambios de propagacion clinica, la meta es leer la nota completa y decidir que regiones requieren actualizacion consistente, sin reescribir toda la nota ni tocar una sola frase aislada.

Ejemplos de regiones potencialmente afectadas:

- motivo de consulta
- enfermedad actual
- antecedentes
- revision por sistemas
- impresion diagnostica
- analisis clinico
- plan

No se planea agregar un modelo de secciones en base de datos por ahora; el LLM las resuelve en runtime.

### 5. Señales del planner sin llamada extra de clasificacion

No agregar una llamada LLM separada para clasificar dificultad.

Extender la salida estructurada del planner existente con campos como:

- `edit_scope`: `"local"` | `"propagation"` | `"reinterpretation"`
- `clinical_impact_level`: `"cosmetic"` | `"factual"` | `"clinical"`
- `affected_sections`: lista de regiones que el planner identifica como afectadas
- `needs_full_note`: bool
- `needs_external_knowledge`: bool

`affected_sections` funciona como un **change map**: el planner le dice al drafter exactamente que regiones tocar, y el drafter no deberia salirse de ese scope.
Esto es mas seguro que dejar al drafter decidir que secciones tocar por su cuenta.

### 6. Multipatch en un solo propose, sin loop multi-turno

El `max_patch_operations` actual esta en 1. Para propagacion y reinterpretacion, se levanta ese limite.

- El drafter ya soporta `patches: list` en su schema `DraftedPatchPlan`.
- Para `local edit`: el drafter emite 1 patch. `max_patch_operations` puede quedar bajo.
- Para `propagation` / `reinterpretation`: el drafter emite N patches (uno por region afectada) en una sola llamada.
- **No tiene valor** un loop multi-turno donde el planner emite un propose por iteracion. Es mas lento, mas fragil y rompe la coherencia del patch set.
- El limite dinamico lo decide el planner via `edit_scope`.

### 7. Flujo read → plan → draft sin precargar contexto innecesario

El planner no debe recibir la nota completa de entrada, porque la mayoria de los mensajes son simples ("Hola", "Agrega mi nombre al final").

Flujo:

1. El planner recibe contexto ligero (workspace_index + summaries de documentos abiertos).
2. **Primer turno del planner:** decide la intencion. Para mensajes simples, responde directo o pide un read_document_span.
3. Si el planner determina que es un caso de propagacion/reinterpretacion, señala `needs_full_note=true` y llama `read_document(mode="full")` el mismo.
4. **Segundo turno del planner:** ya con la nota completa, emite las señales estructuradas (`edit_scope`, `affected_sections`, etc.) y llama la tool de propose.
5. El drafter recibe la nota completa + `affected_sections` como scope explicito.

Esto preserva eficiencia para casos simples y da contexto completo solo cuando se necesita, sin una llamada extra de clasificacion.

### 8. La plantilla del medico como restriccion editorial

La plantilla personalizada del medico se trata como:

- estructura esperada
- tono
- nivel de detalle
- preferencias de secciones o estilo documental

No se trata como evidencia clinica.

- `local edit`: no se necesita la plantilla.
- `propagation` / `reinterpretation`: el planner señala `needs_template: true`. El drafter recibe la plantilla (o regiones relevantes) como bloque `<doctor_template_structure>` junto con la nota completa. Sirve para preservar headings, estilo y saber que secciones usa el medico.

### 9. Politica de seguridad clinica para cambios automaticos

#### El writer puede proponer sin preguntar:

- **Propagacion factual:** agregar un dato a las secciones donde corresponde ("paciente embarazada 10 semanas" → antecedentes + impresion)
- **Consistencia logica:** si el medico agrega un sintoma, reflejarlo en analisis donde se discute
- **Borrados explicitos:** si el medico pide "quita X del plan", quitarlo

#### Proponer pero marcar con impacto alto en review:

- **Cambio de impresion/diagnostico:** agrega o modifica un diagnostico. Se propone, pero la review UI lo marca como `clinical_impact: high`
- **Cambio de plan:** cualquier modificacion al plan se marca porque el plan es lo que impulsa la atencion al paciente

#### No hacer automaticamente:

- Agregar medicamentos, dosis o tratamientos no mencionados por el medico
- Sugerir examenes no implicados por la conversacion
- Eliminar diagnosticos diferenciales sin instruccion explicita
- Cambiar estratificaciones de riesgo

### 10. Señales de review para el frontend

#### Header del patch set:

- `edit_scope`: "Edicion local" / "Propagacion clinica" / "Reinterpretacion clinica"
- `affected_sections`: lista de regiones tocadas
- Rationale breve del planner

#### Por patch:

- Region/seccion
- Tipo de operacion (replace/insert/delete)
- `clinical_impact`: cosmetic / factual / clinical
- Diff (before/after)

#### Agrupacion:

Patches agrupados por region semantica, no como lista plana. El medico debe ver "estos 3 cambios en impresion + plan son porque agregaste embarazo."

#### Aviso de escalacion:

Si `needs_external_knowledge=true` pero no hay RAG disponible: "Este cambio podria beneficiarse de consulta con guias clinicas. El ajuste propuesto se basa solo en el contexto de la nota."

---

## Estrategia para RAG / agente clinico

### Decision: el writer primero, RAG despues

El documento agent (writer) se desarrolla primero. El LLM ya tiene suficiente conocimiento medico general para manejar la gran mayoria de cambios clinicos si se le instruye bien a razonar.

RAG se agrega despues como una **capacidad adicional**, no como prerequisito.

### Cuando basta el writer actual (con buen prompting):

| Caso                                                        | Por que basta                                                |
| ----------------------------------------------------------- | ------------------------------------------------------------ |
| "Agrega dolor de cabeza" → propagar a HPI, assessment, plan | Razonamiento clinico basico dentro de la nota                |
| "Embarazo 10 semanas + ajustar plan"                        | Propagacion factual + cautela. No inventar manejo especifico |
| Traducciones, typos, inserts simples                        | Trabajo textual puro                                         |
| Borrar frase, reordenar seccion                             | Trabajo estructural puro                                     |

### Cuando se necesitara RAG (futuro):

| Caso                                                      | Por que no basta el writer         |
| --------------------------------------------------------- | ---------------------------------- |
| "Esta contraindicado este medicamento para su condicion?" | Conocimiento farmacologico externo |
| "Que dice la guia mas reciente sobre ITU en embarazo?"    | Evidencia clinica externa          |
| Justificacion clinica profunda con citas                  | Requiere fuentes verificables      |

### Señal de escalacion

El campo `needs_external_knowledge` del planner es el hook.
Cuando es `true` y no hay RAG:

- el writer puede pedir aclaracion al medico
- o responder con caveat explicito de que no tiene acceso a guias externas

Cuando RAG exista:

- el writer invoca un subagente o tool de busqueda clinica
- incluye el contexto recuperado como evidencia antes de redactar

### Forma del futuro agente clinico

Todavia por decidir si sera:

- un subagente invocado por el planner del document agent
- un agente paralelo seleccionable por el usuario (ej. "modelo rapido para ediciones / modelo inteligente para consultas clinicas")
- o ambos segun el caso

Lo que si esta claro:

- no bloquea el desarrollo actual del document agent
- la interfaz de invocacion sera una tool o un subgraph, no una reescritura del planner
- el planner del document agent ya produce la señal (`needs_external_knowledge`) que activaria la escalacion

### Valor de RAG mas alla de la precision

Aunque en muchos casos el LLM general ya sea suficiente, RAG podria aportar:

- **Confianza del medico:** saber que el copiloto consulta bases de conocimiento da mas seguridad
- **Trazabilidad:** citar fuentes especificas en el patch rationale
- **Diferenciacion de producto:** feature vendible incluso si el impacto en precision no es dramatico en todos los casos

Esto no cambia la prioridad (document agent primero), pero justifica planear la interfaz de invocacion desde ahora.

---

## Heuristica para cambios grandes

Si entra un nuevo dato con impacto clinico claro, el writer deberia:

1. leer la nota completa (`read_document(mode="full")`)
2. identificar regiones semanticas afectadas
3. decidir si el caso es propagacion factual o reinterpretacion
4. producir un `patch set` multipatch con un patch por region
5. explicar brevemente por que toco esas regiones (rationale del patch set)

Si para seguir hace falta conocimiento externo o hay demasiada ambiguedad:

1. pedir aclaracion al medico
2. o (futuro) escalar a capacidad clinica con RAG/search

---

## Preguntas resueltas

- **Que tan automatico debe ser el cambio de impresion diagnostica?**
  Resuelto: el writer puede proponerlo automaticamente, pero el review lo marca como `clinical_impact: high`. El medico decide en review.

- **Multipatch o multi-turno?**
  Resuelto: multipatch en un solo propose. Sin loop multi-turno.

- **Mandar nota completa al planner siempre?**
  Resuelto: no. El planner arranca ligero. Solo lee `mode="full"` cuando el determina que lo necesita.

- **Seccion como entidad en base de datos?**
  Resuelto: no por ahora. Las secciones son regiones semanticas que el LLM identifica en runtime sobre texto plano.

- **RAG antes o despues del document agent?**
  Resuelto: despues. El LLM tiene suficiente conocimiento clinico general. RAG se agrega como capacidad incremental.

## Preguntas abiertas

- Que partes de la plantilla del medico son solo estilo y cuales representan preferencias clinicas reales que deberian influir en el razonamiento?
- Cual deberia ser el `max_patch_operations` dinamico para propagation/reinterpretation? (5? 8? depende de las regiones detectadas?)
- Como se comporta el drafter con token budget limitado (1600 tokens hoy) cuando tiene que emitir 4-5 patches? Probablemente hay que subirlo para multi-patch.
- Necesitamos validacion de que los patches del drafter cubren todas las `affected_sections` del planner y no se saltan ninguna?
- El aviso de escalacion ("este cambio podria beneficiarse de guias clinicas") lo muestra el chat inline o aparece en la review UI?

---

## Roadmap de implementacion (prioridad tentativa)

### P0 — Habilitar writer multipatch coherente

1. **Extender señales del planner** — agregar `edit_scope`, `affected_sections`, `clinical_impact_level`, `needs_full_note`, `needs_external_knowledge` al schema estructurado del planner.
2. **Levantar `max_patch_operations`** — hacerlo dinamico segun `edit_scope`. Local=1, propagation/reinterpretation=N.
3. **Ajustar prompt del drafter** — recibir `affected_sections` como scope explicito. Subir token budget para multi-patch.
4. **Ajustar routing del graph** — si `needs_full_note`, asegurar que la nota completa se leyo antes de llegar al propose.

### P1 — Mejorar calidad del razonamiento clinico

5. **Prompt de razonamiento clinico** — instruir al drafter con politica de seguridad clinica (que puede proponer, que no, que marcar high impact).
6. **Integracion de plantilla del medico** — señal `needs_template` del planner; pasar template como contexto editorial al drafter en propagation/reinterpretation.
7. **Validar coherencia** — post-check de que los patches emitidos cubren las `affected_sections` del plan.

### P2 — Review UX mejorada

8. **Señales en patch set** — `edit_scope`, `affected_sections`, `clinical_impact` por patch. Agrupar por region semantica.
9. **Badge de impacto clinico** — indicador visual (cosmetic/factual/clinical) por patch.
10. **Aviso de escalacion** — cuando `needs_external_knowledge=true` sin RAG.

### P3 — Capacidad clinica con RAG (futuro)

11. **Diseñar interfaz de invocacion** — tool del planner o subgraph.
12. **Implementar subagente o tool de busqueda clinica.**
13. **Integrar contexto recuperado en drafter.**
14. **Evaluar impacto en precision y confianza del medico.**

- Que partes de la plantilla del medico son solo estilo y cuales representan preferencias clinicas reales que deberian influir en el razonamiento?
- Conviene mostrar en review una etiqueta del tipo `local edit`, `clinical fact propagation` o `clinical reinterpretation` para que el medico entienda el alcance del cambio?
