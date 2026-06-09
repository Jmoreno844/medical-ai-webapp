# worker-runtime

Paquete compartido para infraestructura comun de workers privados Cloud Run.

## Alcance

`worker-runtime` centraliza piezas operativas reutilizables:

- auth de Cloud Tasks
- backend client base con ID token
- logging / observability / tracing
- factories y helpers LLM
- settings base para workers

No define prompts, schemas de negocio ni processors clinicos/documentales.

## `.env.local`

Este paquete no tiene un `.env.local` propio ni debe convertirse en una fuente de verdad de configuracion.

`BaseWorkerSettings` usa:

```python
SettingsConfigDict(env_file=".env.local", ...)
```

pero ese archivo se resuelve desde el servicio consumidor, por ejemplo:

- `transcription_worker/.env.local`
- `document_generation_worker/.env.local`
- `clinical_extraction_worker/.env.local`

En otras palabras: `worker-runtime` es una libreria importable, no un servicio ejecutable con entorno independiente.

## Uso

Cada worker extiende `BaseWorkerSettings` con sus variables especificas y reusa los helpers compartidos sin duplicar bootstrap operativo.
