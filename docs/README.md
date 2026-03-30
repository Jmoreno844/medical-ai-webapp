# Documentación del Proyecto AI Médico

Bienvenido a la documentación central del Proyecto AI Médico. Este sistema es una plataforma fullstack diseñada para asistir a profesionales médicos en la generación de documentación clínica (SOAP, notas de evolución, etc.) a partir de grabaciones de audio de las consultas, utilizando inteligencia artificial.

## Índice de Documentación

| Sección | Descripción |
|---------|-------------|
| [**Guía de Inicio Local**](setup-local.md) | Pasos para levantar todo el ecosistema en tu máquina (Docker, Cloud Functions locales, ngrok). |
| **Arquitectura** | |
| ↳ [Visión General del Sistema](architecture/system-overview.md) | El "Big Picture": diagramas de arquitectura, flujos de datos y cómo interactúan los componentes. |
| ↳ [Base de Datos](architecture/database.md) | Modelo de datos, esquema ERD y decisiones sobre PostgreSQL/SQLite. |
| ↳ [Autenticación y JWT](architecture/auth-and-jwt.md) | Contratos de tokens, claims, autenticación de sesión y comunicación entre servicios. |
| **Guías Operacionales** | |
| ↳ [Logging y Observabilidad](guides/logging.md) | Políticas de logging para frontend, backend y Cloud Functions. |
| ↳ [Secretos y Entornos](guides/secrets-and-environments.md) | Variables de entorno requeridas y configuración por entorno (dev, test, prod). |
| ↳ [Docker](guides/docker.md) | Estructura y uso de los Dockerfiles y Docker Compose en el proyecto. |
| **Referencia** | |
| ↳ [Estándares de Backend](reference/backend-standards.md) | Normas de calidad, convenciones de código y arquitectura objetivo para Django. |
| ↳ [Mapa de Renombrado (Inglés)](reference/english-rename-map.md) | Correspondencia de términos tras la migración del código al inglés. |
| **Decisiones de Arquitectura (ADRs)** | |
| ↳ [Índice de ADRs](decisions/README.md) | Registro de decisiones arquitectónicas importantes tomadas durante el desarrollo. |
