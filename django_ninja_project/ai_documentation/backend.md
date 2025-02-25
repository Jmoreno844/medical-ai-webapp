Rules for the medical dashboard application using Django and Django Ninja, designed to handle sensitive medical data with robust security and performance in production.

Instructions

# Backend Rules (Enhanced Readability & Additional Security Notes)

## Medical Dashboard & Django Ninja

### Django Best Practices

- **Project Structure**  
  Follow Django’s standard structure (settings, modular apps, etc.). Keep apps within `medical_dashboard/` if applicable.
- **Built-in Security**  
  Rely on Django’s CSRF, session management, and HTTPS enforcement. Reference official Django security docs.

### Django Ninja Best Practices

- **Schema Validation**  
  Utilize Pydantic models for input validation; always use type hints.
- **OpenAPI Documentation**  
  Keep API endpoints well-documented, auto-generating docs from Ninja.

### Security Features

- **Role-Based Access Control (RBAC)**  
  Use `django.contrib.auth` for roles (e.g., doctors, admins).
- **Token-Based Auth**  
  Integrate Django Ninja’s `HttpBearer` or OAuth2 in sync with Django’s authentication backend.
- **ORM Safety**  
  Lean on Django ORM for queries; avoid raw SQL to reduce injection risks.

### Error Handling & Logging

- **Exceptions**  
  Use Django middleware or Ninja’s exception handlers. Avoid leaking sensitive data in error messages.
- **Secure Logging**  
  Redact PII; align logs with HIPAA/GDPR if handling medical data.

### Performance Optimization

- **Caching**  
  Use `django-redis` or external backends for caching and keep data encrypted at rest.
- **Environment Variables**  
  Store secrets in `.env` files or a vault (e.g., AWS Secrets Manager).

### File Handling

- **Encrypted Storage**  
  Consider `django-storages` with AWS S3 or similar, ensuring encryption in transit and at rest.
- **Access Controls**  
  Restrict file access to authorized users only.

### Maintenance

- **Continuous Updates**  
  Apply Django security patches. Use tools (e.g., Dependabot) to keep dependencies secure.
- **Static Analysis**  
  Use Bandit or similar to catch vulnerabilities early.

### Component Structure

- **Models**  
  Keep indexes and constraints on sensitive tables.
- **Schemas**  
  Validate request/response data in Pydantic models.
- **Views/APIs**  
  Integrate authentication checks (`@permission_required`) or custom decorators.
- **Helpers**  
  Centralize encryption/decryption or utility methods to standardize usage.

### Additional Security Considerations

- **HTTPS & HSTS**  
  Enable `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, and `SECURE_HSTS_SECONDS`.
- **Database Security**  
  Ensure TLS, field-level crypto for sensitive data, and robust indexing.
- **Rate Limiting**  
  Throttle API calls to prevent DDoS or brute-force attempts.
- **Auditing & Compliance**  
  Conduct regular security audits and store credentials securely (HashiCorp Vault, AWS Secrets Manager, etc.).
- **WAF & CDN**  
  Consider Cloudflare or similar for DDoS protection and additional filtering.
