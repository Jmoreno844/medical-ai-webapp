# Cloud Run, concurrencia y pgvector

Recordatorio operativo para cuando se implemente fan-out concurrente hacia Gemini y consultas paralelas a `pgvector` dentro del mismo servicio en Cloud Run.

## Lo que si importa configurar bien

### Cloud Run concurrency

El valor por defecto de Cloud Run suele ser `80` requests concurrentes por instancia. Si hay conexiones SSE de larga duracion, requests normales y fan-out concurrente a Gemini, conviene revisar esto y probablemente subirlo a algo como `250`.

Punto a recordar:

- esto solo tiene sentido mientras la mayor parte de la carga siga siendo I/O-bound y no CPU-bound
- si la latencia sube o la CPU empieza a saturarse, hay que reevaluar el numero real de concurrencia por instancia

### Cloud SQL connections

Este es probablemente el punto mas facil de subestimar.

Si varios medicos disparan multiples queries de `pgvector` en paralelo, el limite real puede aparecer antes en PostgreSQL que en Cloud Run.

Punto a recordar:

- revisar reutilizacion de conexiones
- revisar pooling real del driver / stack usado en produccion
- no asumir que la app escala solo porque Cloud Run acepta mas requests

Ejemplo orientativo:

```python
DATABASES = {
    "default": {
        # ...
        "CONN_MAX_AGE": 600,
        "OPTIONS": {
            "MAX_CONNS": 20,
        },
    }
}
```

La idea no es copiar esta configuracion literal sin validar el driver y el pool real usado por Django en produccion. El recordatorio importante es que el riesgo principal puede estar en el numero de conexiones concurrentes a Cloud SQL.

### Cloud Run timeout

Si el flujo completo de fan-out y reranking tarda solo unos pocos segundos, el timeout no deberia ser problema, pero no conviene olvidarlo.

Punto a recordar:

- no dejar timeouts demasiado cortos si el mismo servicio tambien mantiene conexiones SSE de larga duracion
- revisar tanto timeout del request como comportamiento de conexiones largas

### SSE inactivas

Si hay SSE abiertas mucho tiempo, un medico que deje el sistema abierto puede mantener la instancia viva y facturando innecesariamente.

Punto a recordar:

- implementar timeout de inactividad en frontend o en `asyncio`
- cerrar la conexion SSE si lleva, por ejemplo, 10 minutos sin actividad

## Failure mode importante

Si se usa `asyncio.gather(...)` para reranking concurrente con Gemini, no conviene que una sola llamada fallida bloquee todo el resultado.

```python
results = await asyncio.gather(
    rerank_cie10(entity_1, candidates_1),
    rerank_cie10(entity_2, candidates_2),
    rerank_cups(entity_3, candidates_3),
    return_exceptions=True,
)

for entity, result in zip(entities, results):
    if isinstance(result, Exception):
        suggestions[entity] = pgvector_candidates[entity][:3]
    else:
        suggestions[entity] = result
```

La idea del fallback es:

- si Gemini responde bien, mostrar sugerencias rerankeadas
- si Gemini falla o se demora demasiado, mostrar candidatos crudos desde `pgvector`

Asi la experiencia del medico no queda bloqueada por una falla parcial.

## Resumen

Si se implementa este tipo de fan-out, no olvidar revisar al menos estos cuatro puntos:

- `Cloud Run concurrency`
- conexiones a `Cloud SQL`
- timeout de requests / SSE
- fallback de fallos parciales en `asyncio.gather(...)`

Esta nota existe como recordatorio para no enfocarse solo en la logica de negocio y olvidar la configuracion operativa alrededor.
