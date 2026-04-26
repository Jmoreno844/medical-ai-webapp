# ADR-007: Anchors por Contenido y Lectura Completa Explícita en el Writer Flow

## Estatus

Aceptado

## Contexto

El `document helper` del copiloto ya cierra el flujo `patch -> review -> apply`, pero aparecieron dos límites claros en la surface original del runtime:

- el agente dependía demasiado de `read_document_summary` + `read_document_span`, incluso en pedidos como "agrega esto al final", donde un span inicial no basta para ubicar el cambio con seguridad
- el backend ya resuelve patches por anchors textuales y soporta operaciones más ricas (`insert_before`, `insert_after`, `delete_span`) que la surface pública inicial del agente

Además, los offsets por sí solos no son una estrategia suficientemente robusta para documentos clínicos que pueden cambiar entre lectura y apply. El backend ya trata `exactText`, `prefixText` y `suffixText` como la señal principal para reubicar un patch.

## Decisión

El writer flow del copiloto adopta estas reglas:

1. Los patches se anclan principalmente por contenido:
   - `exactText`
   - `prefixText`
   - `suffixText`
   - `startOffset` / `endOffset` quedan como ayudas secundarias

2. El runtime expone una tool explícita `read_document(document_id, mode)` para lecturas:
   - `summary`
   - `excerpt`
   - `full`

3. `read_document_span` queda reservada para lecturas focalizadas o resolución de anchors; no se usa como sustituto implícito de "leer todo el documento".

4. La surface pública de patches del agente debe reflejar las operaciones reales del backend:
   - `propose_replace_span`
   - `propose_insert_after_span`
   - `propose_insert_before`
   - `propose_delete_span`

5. Para cambios al inicio/final del documento o cambios amplios, el planner debe preferir `read_document(mode="full")` antes de proponer el patch.

## Alternativas consideradas

### 1. Seguir solo con `read_document_span`

Se descartó porque empuja al modelo a inferir estructura global del documento a partir de un excerpt parcial, lo que vuelve frágiles los inserts al inicio/final y las reescrituras amplias.

### 2. Basar la estrategia principalmente en offsets

Se descartó porque los offsets se vuelven obsoletos fácilmente si el documento cambia. El fallback por contenido ya existe en backend y es más robusto para apply diferido.

### 3. Exponer solo `replace_span`

Se descartó porque el backend ya soporta inserciones y borrados anclados. Mantener una surface más pobre en el agente introduce fricción innecesaria y peores planes del modelo.

## Consecuencias

### Positivas

- El runtime puede resolver mejor pedidos como "agrega al final", "inserta antes de..." o "borra esta frase".
- La surface del agente queda más alineada con el contrato real de apply en FastAPI.
- El sistema depende menos de offsets frágiles y más de anchors textuales reubicables.

### Negativas / Retos

- La surface del agente crece y exige instrucciones más claras para elegir entre `summary`, `span` y `full`.
- Leer el documento completo aumenta costo cuando se abuse de `mode="full"`, por lo que el planner debe reservarlo para casos donde realmente aporta.
- Sigue pendiente una optimización futura para leer regiones terminales/iniciales sin pedir siempre el documento completo.
