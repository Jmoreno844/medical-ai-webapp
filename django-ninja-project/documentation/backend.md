# Backend — Normas de calidad y arquitectura objetivo

> Este documento contiene las **normas y estándares** que el proyecto debe cumplir.
> No describe el estado actual del sistema; para eso consulta los siguientes documentos:
>
> | Documento | Contenido |
> |-----------|-----------|
> | [`system_map.md`](system_map.md) | Mapa de servicios, inventario de endpoints, variables de entorno |
> | [`flows.md`](flows.md) | Flujos de transcripción, autenticación y generación de documentos |
> | [`database.md`](database.md) | Esquema real de BD, ERD, índices, migraciones |
> | [`jwt_and_auth_contracts.md`](jwt_and_auth_contracts.md) | Contratos JWT y variables de entorno de auth |

---

## Dependencias Python (`uv`)

El backend usa **[uv](https://docs.astral.sh/uv/)** (no Poetry): `pyproject.toml` + `uv.lock`.

- Instalar dependencias: `uv sync` (incluye el grupo `dev` por defecto).
- Solo producción (equivalente a Docker): `uv sync --no-dev`.
- Comandos Django: `uv run python manage.py …`
- Añadir paquete: `uv add <nombre>` · dependencias de desarrollo: `uv add --group dev <nombre>`.

---

## Code Structure & Best Practices

### Architecture

Follow Django's app-based structure for modularity
Implement service-layer pattern to separate business logic from views
Use dependency injection where appropriate
Ensure proper separation of concerns

API Design

Implement RESTful principles consistently
Use proper HTTP status codes and methods
Structure endpoints logically (e.g., /api/v1/patients/{id}/recordings)
Implement pagination for list endpoints
Return clear error messages and validation feedback

Code Style

Follow PEP 8 standards
Use type hints throughout the codebase
Write descriptive variable and function names
Keep functions small and focused (single responsibility)
Use Django's built-in functionality where possible

Documentation Requirements
API Documentation

Add comprehensive docstrings to all API endpoints
Include parameter descriptions, types, and example values
Document possible response codes and their meanings
Use Django Ninja's automatic OpenAPI documentation features

Code Documentation

Write clear docstrings for all non-trivial functions and classes
Document complex algorithms or business rules with comments
Include usage examples for reusable components
Document assumptions and edge cases

Project Documentation

Create clear README.md with setup instructions
Document environment variables and configuration options
Include database schema diagrams or descriptions
Add deployment guides and requirements

Security Best Practices
Authentication & Authorization

Implement proper JWT token handling with expiration
Use refresh tokens with secure rotation
Implement role-based access control
Never store sensitive data in tokens
Implement MFA for admin accounts

Data Protection

Encrypt sensitive data at rest in the database
Use HTTPS for all API communication
Implement proper field-level permissions
Sanitize all user inputs
Implement audit logging for PHI access

HIPAA Compliance

Implement comprehensive audit trails
Include required HIPAA fields in logs (who, what, when, where)
Use proper data retention policies
Implement data export capabilities for patient requests
Add automatic session timeouts

Code Security

Prevent SQL injection via Django ORM and parametrized queries
Implement rate limiting for API endpoints
Add CSRF protection for browser-based access
Set secure cookie flags
Regularly update dependencies

Testing Focus

Write comprehensive unit tests (aim for >80% coverage)
Include security-focused tests (authentication bypass, injection)
Test authorization edge cases
Write integration tests for critical flows
Implement API contract testing

Database Considerations

Use migrations properly
Implement indexes for frequently queried fields
Design with performance in mind (avoid N+1 queries)
Use proper constraints (foreign keys, unique constraints)
Consider table partitioning for large datasets

Error Handling

Implement global exception handling
Log errors with appropriate context
Return user-friendly error messages
Include correlation IDs for tracking issues
Handle expected errors gracefully

Performance

Cache frequently accessed data
Use select_related and prefetch_related to avoid N+1 queries
Optimize database access patterns
Consider async views for long-running operations
Implement database connection pooling
