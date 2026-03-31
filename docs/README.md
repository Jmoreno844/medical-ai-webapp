# Documentación del Proyecto AI Médico

La documentación está organizada con una capa global y luego una entrada por servicio. Si quieres entender el sistema completo, empieza por `architecture/`. Si quieres trabajar en una parte concreta, entra por `backend/`, `frontend/` o `cloud-functions/`.

## Empezar por aquí

| Sección | Descripción |
|---------|-------------|
| [Guía de Inicio Local](setup-local.md) | Levantar DB, backend, frontend y Cloud Functions en local. |
| [Arquitectura global](architecture/system-overview.md) | Big picture del sistema: audio, Django, GCS, Gemini, SSE y callbacks. |
| [Backend](backend/README.md) | Base de datos, auth/JWT, logging, tracing, Docker y entornos del backend. |
| [Frontend](frontend/README.md) | Rutas, contextos, features principales y logging del `webapp/`. |
| [Cloud Functions](cloud-functions/README.md) | Entry points, servicios internos, callbacks a Django y variables clave. |
| [Infraestructura GCP](architecture/gcp-infrastructure.md) | IAM, secrets, lifecycle, naming, Terraform, CI y troubleshooting. |
| [Infra (Terraform)](../infra/README.md) | Bootstrap, primer apply, estado remoto y matiz Terraform vs GitHub Actions. |
| [ADRs](decisions/README.md) | Decisiones arquitectónicas relevantes del proyecto. |
| [Notes](notes/cloud-run-concurrency-y-pgvector.md) | Notas técnicas temporales o de apoyo sobre operación, escala y decisiones aún no formalizadas. |
