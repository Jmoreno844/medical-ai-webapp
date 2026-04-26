# Documentación del Proyecto AI Médico

La documentación está organizada para responder dos preguntas:

1. `¿Cómo funciona el sistema completo?`
2. `¿Dónde cambio algo sin romper contratos sensibles?`

## Empezar por aquí

| Sección | Descripción |
|---------|-------------|
| [Mapa del repositorio](architecture/repo-map.md) | Qué vive en cada carpeta, qué es sensible y dónde editar según el tipo de cambio. |
| [Guía de inicio local](setup-local.md) | Levantar backend, frontend, base de datos y Cloud Functions en local. |
| [Arquitectura global](architecture/system-overview.md) | Big picture del sistema: audio, FastAPI, GCS, Gemini, SSE y callbacks. |
| [Backend](backend/README.md) | Auth/JWT, DB, entornos, logging, tracing y límites del backend. |
| [Frontend](frontend/README.md) | Rutas, contextos, features principales y logging del `webapp/`. |
| [Cloud Functions](cloud-functions/README.md) | Entry points, servicios internos, callbacks al backend y variables clave. |
| [Infraestructura GCP](architecture/gcp-infrastructure.md) | IAM, secrets, lifecycle, naming, Terraform, CI y troubleshooting. |
| [Arquitectura del workspace + copiloto](architecture/ai-agent-workspace.md) | Workspace frontend, boundary del agent runtime y patrón de patches/review. |
| [Deuda técnica canónica](debt/README.md) | Deudas aceptadas y transversales que futuros chats deben tener presentes. |
| [Infra (Terraform)](../infra/README.md) | Bootstrap, primer apply, estado remoto y matiz Terraform vs GitHub Actions. |
| [ADRs](decisions/README.md) | Decisiones arquitectónicas relevantes del proyecto. |
| [Notas](notes/cloud-run-concurrency-y-pgvector.md) | Notas técnicas temporales sobre operación, escala y decisiones aún no formalizadas. |

## Antes de tocar zonas sensibles

- Auth, JWT, SSE o callbacks entre servicios:
  [`backend/auth-and-jwt.md`](backend/auth-and-jwt.md)
- Modelos, migraciones o naming de datos:
  [`backend/database.md`](backend/database.md)
- Deploy, IAM, secrets o service accounts:
  [`architecture/gcp-infrastructure.md`](architecture/gcp-infrastructure.md)
- Cambios estructurales del repo para agentes:
  [`../AGENTS.md`](../AGENTS.md)
