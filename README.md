# Proyecto AI Médico

Plataforma fullstack de documentación médica asistida por IA. Este sistema permite a los profesionales de la salud grabar consultas médicas, transcribir el audio automáticamente y generar documentos clínicos (como notas SOAP o de evolución) utilizando inteligencia artificial.

## Arquitectura Principal

El proyecto se divide en tres componentes principales:

- **`backend/`**: API REST principal construida con Django Ninja y PostgreSQL.
- **`cloud_functions/`**: Funciones serverless en Google Cloud para la transcripción de audio y generación de documentos con IA (Gemini).
- **`webapp/`**: Aplicación frontend construida con React, TypeScript y Vite.

## Documentación

Toda la documentación técnica, guías de arquitectura, configuración y despliegue se encuentra centralizada en la carpeta `docs/`.

👉 **[Ir a la Documentación Principal](docs/README.md)**

### Enlaces Rápidos
- [Guía de Inicio Local](docs/setup-local.md)
- [Visión General del Sistema](docs/architecture/system-overview.md)
- [Registro de Decisiones (ADRs)](docs/decisions/README.md)
