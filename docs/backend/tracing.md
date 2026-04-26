# Distributed tracing (OpenTelemetry)

El stack usa **OpenTelemetry** con propagación **W3C** (`traceparent` / `tracestate`) entre `webapp` → FastAPI → Cloud Functions → FastAPI (callbacks).

## Componentes

| Código | Rol |
|--------|-----|
| `backend_fastapi/app/` | API principal; emite logs y spans del backend |
| [cloud_functions/functions/tracing.py](../../cloud_functions/functions/tracing.py) | Span servidor por request HTTP + `requests` al backend |
| [webapp/src/tracing.ts](../../webapp/src/tracing.ts) | OTLP desde el navegador (opcional) + propagación en XHR/`axios` |

## Variables de entorno (backend y Cloud Functions)

| Variable | Descripción |
|----------|-------------|
| `OTEL_SDK_DISABLED` | `1` / `true` — desactiva export e instrumentación pesada (p. ej. tests). |
| `OTEL_TRACES_EXPORTER` | `none` \| `otlp` \| `gcp` (opcional; si no se define, se infiere). |
| `OTEL_SERVICE_NAME` | Nombre del servicio en el backend de trazas (p. ej. `vexthealth-backend`, `vexthealth-cloud-functions`). |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | URL completa OTLP/HTTP, p. ej. `http://127.0.0.1:4318/v1/traces`. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Base OTLP; si no hay `..._TRACES_...`, se usa `\<base\>/v1/traces`. |
| `OTEL_TRACES_SAMPLER_ARG` | Ratio `0.0`–`1.0` para `TraceIdRatioBased` bajo `ParentBased` (por defecto `1.0`). |
| `OTEL_FORCE_OTLP` | `1` — fuerza OTLP aunque exista `GOOGLE_CLOUD_PROJECT` (útil en portátiles con proyecto GCP en shell). |
| `GOOGLE_CLOUD_PROJECT` / `GCP_PROJECT` | Si están definidos y no se fuerza OTLP, el export por defecto es **Cloud Trace**. |

## GCP (stg / producción)

- En **Cloud Run** y **Cloud Functions**, suele existir `GOOGLE_CLOUD_PROJECT`; el exportador **GCP Trace** usa la cuenta de servicio del workload.
- Concede a esa cuenta el rol **Cloud Trace Agent** (`roles/cloudtrace.agent`) si no viene ya en el rol de ejecución recomendado por GCP.
- El navegador **no** envía trazas directamente a Cloud Trace en el modelo habitual (sin collector expuesto). Las trazas del front en producción suelen limitarse a spans locales o quedar desactivadas (`VITE_OTEL_EXPORTER_OTLP_TRACES_URL` vacío).

### Estado actual en `stg`

- `backend` y `cloud functions` sí pueden compartir el mismo `trace_id` en Cloud Trace cuando la petición pasa por HTTP normal (`FastAPI -> Cloud Function -> callback FastAPI`).
- `webapp` todavía **no** participa en el mismo trace en `stg`: el workflow de frontend no configura `VITE_OTEL_EXPORTER_OTLP_TRACES_URL` y no hay un OTEL collector público/intermedio.
- Hasta montar collector OTLP o un backend OTLP accesible desde navegador, la visibilidad de `stg` es **backend/cloud functions**, no navegador de extremo a extremo.

## Local con Jaeger

1. Levanta Jaeger con OTLP (por ejemplo [docker-compose.tracing.yml](../../docker-compose.tracing.yml) en la raíz del repo).
2. **Backend**: `OTEL_TRACES_EXPORTER=otlp`, `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4318/v1/traces`, `OTEL_SERVICE_NAME=vexthealth-backend`. Si tu shell exporta `GOOGLE_CLOUD_PROJECT`, añade `OTEL_FORCE_OTLP=1`.
3. **Cloud Functions** (emulador Docker): mismo endpoint hacia el host, p. ej. `http://host.docker.internal:4318/v1/traces`.
4. **Webapp**: en `.env.local`, `VITE_OTEL_EXPORTER_OTLP_TRACES_URL=/otel/v1/traces` y `VITE_OTEL_SERVICE_NAME=vexthealth-webapp`. Vite reenvía `/otel/*` al puerto 4318 (ver [webapp/vite.config.ts](../../webapp/vite.config.ts)).

UI Jaeger: `http://localhost:16686`.

## Limitaciones conocidas

- **SSE**: `EventSource` no envía cabeceras W3C; se registra `trace_id` en logs al generar token y al conectar el stream en `backend_fastapi/app/domains/documents/sse_api.py`, no un span continuo en el navegador.
- **Subida GCS** (`fetch` a signed URL): span cliente local `gcs.signed_url_upload` sin propagación a GCS.
- **Hilo de generación**: el POST en segundo plano reutiliza el contexto OTel del request que lo disparó (`backend_fastapi/app/domains/documents/generation_runner.py`).

El `process_id` de negocio sigue siendo el identificador de correlación del flujo de generación; no sustituye al `trace_id`.
